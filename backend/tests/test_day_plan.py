"""Meera's day planning: when to go, when not to, and the trip offer. Facts come only from the engine."""
import asyncio
import copy
import json
from datetime import datetime

import pytest
from sqlmodel import Session

from app.db import engine
from app.models import User
from app.routers import assistant as assistant_router
from app.services import advisor, assistant, assistant_tools as tools, forecast, llm, risk_engine
from tests.test_api import client, register  # noqa: F401  (fixture)
from tests.test_assistant import _fake_model, say


@pytest.fixture(autouse=True)
def _fresh():
    assistant_router.limiter.reset()
    llm.reset_pool()
    scenario = forecast.get_scenario()
    yield
    llm.reset_pool()
    forecast.set_scenario(scenario)


def _ctx(client, scenario):
    uid, headers = register(client)
    forecast.set_scenario(scenario)
    with Session(engine) as s:
        me = s.get(User, uid)
        ctx = asyncio.run(advisor.compute(s, me.home_lat, me.home_lon, me.boat_type, days=assistant.FORECAST_DAYS))
    return ctx, headers


def _engine_level(ctx, day_index, hour):
    d = ctx["dates"][day_index]
    return next(h.level for h in ctx["hours"] if h.time.date() == d and h.time.hour == hour)


# ---- the plan itself (pure) ----------------------------------------------------------

def test_calm_day_gets_the_engine_window_and_an_offer(client):
    ctx, _ = _ctx(client, "calm")
    plan = tools.day_plan(ctx, 1)
    w = ctx["days"][1]["window"]
    assert plan["data"] == "ok" and plan["best_window"]["leave_from"] == tools.tx.fmt_time(w["start"], "en")
    assert plan["best_window"]["return_by"] == tools.tx.fmt_time(w["return_by"], "en")
    assert plan["offer"] and plan["offer"]["return_hour"] > plan["offer"]["depart_hour"]
    spoken = tools.plan_spoken(plan)
    assert "between" in spoken and "be back by" in spoken and "Shall I plan a trip" in spoken


@pytest.mark.parametrize("scenario", ["calm", "worsening", "storm"])
def test_offered_hours_are_always_safe(client, scenario):
    ctx, _ = _ctx(client, scenario)
    for i in range(len(ctx["days"])):
        plan = tools.day_plan(ctx, i)
        if plan["offer"]:
            for hour in range(plan["offer"]["depart_hour"], plan["offer"]["return_hour"]):
                assert _engine_level(ctx, i, hour) == risk_engine.SAFE
        if plan["best_window"] is None:
            assert plan["offer"] is None


def test_storm_day_says_do_not_go(client):
    ctx, _ = _ctx(client, "storm")
    plan = tools.day_plan(ctx, 1)
    assert plan["best_window"] is None and plan["offer"] is None and plan["avoid"]
    assert plan["avoid"][0]["level"] == risk_engine.UNSAFE
    spoken = tools.plan_spoken(plan)
    assert "wouldn't go out" in spoken and "Shall I" not in spoken


def test_avoid_runs_carry_the_wind_and_direction(client):
    ctx, _ = _ctx(client, "storm")
    a = tools.day_plan(ctx, 1)["avoid"][0]
    assert a["wind_kmh_max"] is not None and a["reason"] and a["cause"]
    phrase = tools._wind_phrase({**a, "cause": "wind_speed"})
    if a["wind_from"]:
        assert len(phrase.split("from the ")[1]) > 2  # "west", not "W"


def test_wind_is_only_blamed_when_the_engine_blamed_it():
    """Seen live: a CAUTION evening (darkness) was spoken as 'the wind picks up to 4 kilometres an hour'."""
    night = {"wind_kmh_max": 4, "wind_from": "NE", "cause": "night", "reason": "It is dark."}
    windy = {"wind_kmh_max": 32, "wind_from": "W", "cause": "wind_speed", "reason": "Wind 32 km/h."}
    assert tools._wind_phrase(night) == ""
    assert tools._wind_phrase(windy) == "the wind picks up to 32 kilometres an hour from the west"


def test_stale_forecast_is_never_called_safe(client):
    ctx, _ = _ctx(client, "calm")
    ctx = {**ctx, "too_old": True}
    plan = tools.day_plan(ctx, 1)
    assert plan["data"] == "stale" and plan["best_window"] is None and plan["offer"] is None
    spoken = tools.plan_spoken(plan)
    assert "CAUTION" in spoken and "can't call any hour safe" in spoken


def test_missing_numbers_are_said_out_loud(client):
    ctx, _ = _ctx(client, "calm")
    rows = copy.deepcopy(ctx["rows"])
    for r in rows:
        r["wave_height"] = r["wind_speed"] = None
    plan = tools.day_plan({**ctx, "rows": rows}, 1)
    assert plan["data"] == "missing" and plan["offer"] is None
    assert "don't have forecast numbers" in tools.plan_spoken(plan) and "CAUTION" in tools.plan_spoken(plan)


def test_period_limits_the_hours(client):
    ctx, _ = _ctx(client, "calm")
    plan = tools.day_plan(ctx, 1, "afternoon")
    assert plan["hours"] and all(12 <= h["hour"] < 17 for h in plan["hours"])
    assert tools.detect_period("how is the early morning?") == "early morning"
    assert tools.detect_period("this afternoon") == "afternoon"


# ---- through the assistant, without keys -----------------------------------------------

def test_when_should_i_go_then_yes_books_the_offered_trip(client):
    _, headers = register(client)
    forecast.set_scenario("calm")
    out = say(client, headers, "When should I go tomorrow?")
    assert out["source"] == "rules" and "Shall I plan a trip" in out["reply"] and out["proposal"] is None
    plan = client.get("/assistant/day-plan", headers=headers, params={"day_index": 1}).json()
    done = say(client, headers, "yes")
    assert done["action"] == "confirm_schedule" and done["proposal"]["status"] == "scheduled"
    assert done["proposal"]["depart_label"] == plan["offer"]["depart_label"]


def test_offer_declined_books_nothing(client):
    _, headers = register(client)
    forecast.set_scenario("calm")
    say(client, headers, "what's the best time to go tomorrow?")
    assert "won't plan it" in say(client, headers, "no thanks")["reply"]
    assert client.get("/schedule", headers=headers).json() == []


def test_offer_is_rechecked_when_the_sea_changes(client):
    _, headers = register(client)
    forecast.set_scenario("calm")
    say(client, headers, "when should I go tomorrow?")
    forecast.set_scenario("storm")  # the forecast turns before the fisher says yes
    out = say(client, headers, "yes")
    assert out["proposal"] is None and "can't schedule" in out["reply"] and "UNSAFE" in out["reply"]
    assert client.get("/schedule", headers=headers).json() == []


def test_is_an_hour_ok(client):
    _, headers = register(client)
    forecast.set_scenario("storm")
    out = say(client, headers, "Is 4 AM ok tomorrow?")
    assert "4 AM" in out["reply"] and "UNSAFE" in out["reply"] and "wouldn't go out" in out["reply"]
    assert out["proposal"] is None


def test_what_is_the_sea_like_this_afternoon(client):
    _, headers = register(client)
    forecast.set_scenario("calm")
    out = say(client, headers, "What's the sea like tomorrow afternoon?")
    assert "afternoon" in out["reply"].lower() and "SAFE" in out["reply"]


def test_day_plan_endpoint_shape(client):
    _, headers = register(client)
    forecast.set_scenario("calm")
    body = client.get("/assistant/day-plan", headers=headers, params={"day_index": 1}).json()
    for key in ("day_index", "verdict", "data", "best_window", "offer", "avoid", "harbour_mouth_at_departure",
                "harbour_mouth_safe_crossing", "hours", "spoken"):
        assert key in body
    assert {"leave_from", "leave_until", "return_by", "start", "end", "return_by_at"} <= set(body["best_window"])
    assert client.get("/assistant/day-plan", headers=headers, params={"day_index": 9}).status_code == 422


# ---- with a (fake) model ---------------------------------------------------------------

def test_model_plan_reply_that_approves_unsafe_hours_is_replaced(client, monkeypatch):
    _, headers = register(client)
    forecast.set_scenario("storm")
    replies, sent = [], []
    _fake_model(monkeypatch, replies, sent)
    replies.append(json.dumps({"reply": "Let me look at the day.", "action": {"type": "plan_day", "day_index": 1}}))
    replies.append(json.dumps({"reply": "Tomorrow morning is safe, go at 5!", "action": {"type": "none"}}))
    out = say(client, headers, "when should I go tomorrow?")
    assert "go at 5" not in out["reply"] and "wouldn't go out" in out["reply"]
    assert '<tool_result name="plan_day">' in sent[1][-1]["content"] and '"best_window": null' in sent[1][-1]["content"]


def test_offer_made_without_the_tool_still_books_engine_hours(client, monkeypatch):
    """Seen live: the model answered from its 7-day facts and offered a trip without calling plan_day."""
    _, headers = register(client)
    forecast.set_scenario("calm")
    replies, sent = [], []
    _fake_model(monkeypatch, replies, sent)
    replies.append(json.dumps({"reply": "Tomorrow looks safe from 6 AM to 6 PM. Want me to set a trip for you?",
                               "action": {"type": "none"}}))
    replies.append(json.dumps({"reply": "Done!", "action": {"type": "confirm_schedule"}}))
    say(client, headers, "When should I go tomorrow?")
    plan = client.get("/assistant/day-plan", headers=headers, params={"day_index": 1}).json()
    done = say(client, headers, "yes")
    assert done["proposal"]["status"] == "scheduled"
    assert done["proposal"]["depart_label"] == plan["offer"]["depart_label"]
    assert done["proposal"]["return_label"] == plan["offer"]["return_label"]  # engine hours, not "6 PM"


def test_yes_to_an_offer_books_even_if_the_model_just_chats(client, monkeypatch):
    """Seen live: after an offer, the model answered "yes" with action none and asked for times again."""
    _, headers = register(client)
    forecast.set_scenario("calm")
    replies, sent = [], []
    _fake_model(monkeypatch, replies, sent)
    replies.append(json.dumps({"reply": "Tomorrow is SAFE after 6 AM. Want me to plan a trip for a safer time?",
                               "action": {"type": "none"}}))
    replies.append(json.dumps({"reply": "Sure, what time would you like to leave?", "action": {"type": "none"}}))
    say(client, headers, "Is 4 AM ok tomorrow?")
    done = say(client, headers, "yes")
    assert done["proposal"] and done["proposal"]["status"] == "scheduled" and "what time" not in done["reply"]


def test_offer_regex():
    assert assistant._OFFER.search("Want me to set a trip for you?")
    assert assistant._OFFER.search("Shall I plan a trip from 6 AM to 11 AM?")
    assert assistant._OFFER.search("I'd wait until after 6 AM. Want me to plan a good window for you?")
    assert not assistant._OFFER.search("Want me to explain the harbour mouth?")
    assert not assistant._OFFER.search("Your trip is planned. Stay safe.")


def test_model_plan_reply_is_used_and_offer_is_remembered(client, monkeypatch):
    _, headers = register(client)
    forecast.set_scenario("calm")
    replies, sent = [], []
    _fake_model(monkeypatch, replies, sent)
    replies.append(json.dumps({"reply": "Let me look.", "action": {"type": "plan_day", "day_index": 1}}))
    replies.append(json.dumps({"reply": "Tomorrow's lovely and calm. Want me to plan the trip?", "action": {"type": "none"}}))
    replies.append(json.dumps({"reply": "Great!", "action": {"type": "confirm_schedule"}}))
    out = say(client, headers, "plan my day tomorrow")
    assert out["source"] == "ai" and out["reply"].startswith("Tomorrow's lovely")
    done = say(client, headers, "yes please")
    assert done["proposal"]["status"] == "scheduled" and "Great" not in done["reply"]
