"""Meera in Malayalam: emergency words, no-key answers, go/no-go advice, and the local-time check."""
import asyncio
import json
import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session

from app.db import engine
from app.models import User
from app.routers import assistant as assistant_router
from app.services import advisor, assistant, assistant_tools as tools, forecast, llm, risk_engine
from tests.test_api import client, register  # noqa: F401  (fixture)
from tests.test_assistant import _fake_model, say

ML = re.compile("[ഀ-ൿ]")
LATIN_VERDICT = re.compile(r"\b(SAFE|CAUTION|UNSAFE)\b")


@pytest.fixture(autouse=True)
def _fresh():
    assistant_router.limiter.reset()
    llm.reset_pool()
    scenario = forecast.get_scenario()
    yield
    llm.reset_pool()
    forecast.set_scenario(scenario)


def say_ml(client, headers, text):
    resp = client.post("/assistant/chat", headers=headers, json={"message": text, "language": "ml"})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---- emergency words ------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "രക്ഷിക്കണേ!",
    "ഞങ്ങളുടെ വള്ളം മുങ്ങുന്നു",
    "വെള്ളം കയറുന്നു, സഹായിക്കൂ",
    "വള്ളത്തിൽ തീ പിടിച്ചു",
    "ഒരാൾ കടലിൽ വീണു",
    "എഞ്ചിൻ നിന്നു, ഒഴുകിപ്പോകുന്നു",
    "എൻജിൻ പ്രവർത്തിക്കുന്നില്ല",
    "ഞങ്ങൾക്ക് വഴി തെറ്റി",
    "ഒരാൾക്ക് പരിക്കേറ്റു",
    "സഹായം വേണം",
    "അടിയന്തരം",
])
def test_malayalam_distress_is_an_emergency(text):
    assert assistant.is_emergency(text) is True


@pytest.mark.parametrize("text", [
    "SOS എങ്ങനെ പ്രവർത്തിക്കുന്നു?",
    "അടിയന്തര കോൺടാക്ടുകൾ ആരൊക്കെ?",
    "നാളെ രാവിലെ പോകാമോ?",
    "കടൽ എങ്ങനെയുണ്ട്?",
    "സഹായം എന്താണ്?",
])
def test_malayalam_questions_are_not_emergencies(text):
    assert assistant.is_emergency(text) is False


def test_malayalam_emergency_skips_rate_limit_model_and_guard(client, monkeypatch):
    _, headers = register(client, language="ml")
    monkeypatch.setattr(assistant_router.limiter.windows[0], "limit", 1)
    replies, sent = [], []
    _fake_model(monkeypatch, replies, sent)
    for _ in range(3):
        out = say(client, headers, "രക്ഷിക്കണേ, വള്ളം മുങ്ങുന്നു")
        assert out["action"] == "sos_help" and "1554" in out["reply"] and ML.search(out["reply"])
        assert out["source"] == "rules" and out["language"] == "ml"
    assert sent == []  # no model call


# ---- no-key Malayalam answers ----------------------------------------------------------

def test_profile_language_is_used_without_the_app_sending_it(client):
    _, headers = register(client, language="ml")
    forecast.set_scenario("calm")
    out = say(client, headers, "When should I go tomorrow?")  # typed in English, profile is Malayalam
    assert out["language"] == "ml" and ML.search(out["reply"]) and not LATIN_VERDICT.search(out["reply"])


def test_malayalam_message_is_answered_in_malayalam_even_if_the_app_is_english(client):
    _, headers = register(client, language="en")
    forecast.set_scenario("calm")
    out = say(client, headers, "നാളെ രാവിലെ പോകാമോ?")
    assert out["language"] == "ml" and ML.search(out["reply"])


def test_go_no_go_offer_and_yes_in_malayalam(client):
    _, headers = register(client, language="ml")
    forecast.set_scenario("calm")
    out = say_ml(client, headers, "നാളെ എപ്പോൾ പോകണം?")
    assert out["source"] == "rules" and out["proposal"] is None
    assert ML.search(out["reply"]) and not LATIN_VERDICT.search(out["reply"])
    assert "പ്ലാൻ ചെയ്യട്ടെ" in out["reply"]  # the offer
    plan = client.get("/assistant/day-plan", headers=headers, params={"day_index": 1, "language": "ml"}).json()
    assert plan["lang"] == "ml" and ML.search(plan["spoken"])
    done = say_ml(client, headers, "ശരി")
    assert done["action"] == "confirm_schedule" and done["proposal"]["status"] == "scheduled"
    assert done["proposal"]["depart_label"] == plan["offer"]["depart_label"]
    assert ML.search(done["reply"])
    # the booked hours are SAFE hours
    sched = client.get("/schedule", headers=headers).json()
    assert len(sched) == 1 and sched[0]["verdict"] == risk_engine.SAFE


def test_offer_declined_in_malayalam_books_nothing(client):
    _, headers = register(client, language="ml")
    forecast.set_scenario("calm")
    say_ml(client, headers, "നാളെ എപ്പോൾ പോകണം?")
    out = say_ml(client, headers, "വേണ്ട")
    assert ML.search(out["reply"]) and client.get("/schedule", headers=headers).json() == []


def test_schedule_by_malayalam_voice(client):
    _, headers = register(client, language="ml")
    forecast.set_scenario("calm")
    out = say_ml(client, headers, "നാളെ രാവിലെ ഏഴ് മണിക്ക് പോയി പതിനൊന്ന് മണിക്ക് തിരിച്ചെത്തുന്ന ട്രിപ്പ് പ്ലാൻ ചെയ്യൂ")
    assert out["proposal"] is not None and out["proposal"]["verdict"] == risk_engine.SAFE
    assert ML.search(out["reply"]) and "ഷെഡ്യൂൾ ചെയ്യട്ടെ" in out["reply"]
    done = say_ml(client, headers, "ശരി")
    assert done["proposal"]["status"] == "scheduled" and "ഷെഡ്യൂൾ ചെയ്തു" in done["reply"]


def test_unsafe_hours_are_refused_in_malayalam(client):
    _, headers = register(client, language="ml")
    forecast.set_scenario("storm")
    out = say_ml(client, headers, "നാളെ രാവിലെ 6 മണിക്ക് പോയി 11 മണിക്ക് തിരിച്ചെത്തുന്ന ട്രിപ്പ് പ്ലാൻ ചെയ്യൂ")
    assert out["proposal"] is None and "അപകടം" in out["reply"] and ML.search(out["reply"])
    assert client.get("/schedule", headers=headers).json() == []
    say_ml(client, headers, "നാളെ എപ്പോൾ പോകണം?")  # a storm day: no offer
    assert say_ml(client, headers, "ശരി")["proposal"] is None
    assert client.get("/schedule", headers=headers).json() == []


def test_how_sos_works_in_malayalam_without_a_model(client):
    _, headers = register(client, language="ml")
    out = say_ml(client, headers, "SOS എങ്ങനെ പ്രവർത്തിക്കുന്നു?")
    assert out["source"] == "rules" and "kb:sos" in out["citations"]
    assert "അമർത്തിപ്പിടിക്കുക" in out["reply"] and "1554" in out["reply"]


def test_auto_sos_answer_in_malayalam_keeps_the_waiting_times(client):
    _, headers = register(client, language="ml", boat="non_motorised")
    out = say_ml(client, headers, "ഓട്ടോമാറ്റിക് SOS എപ്പോഴാണ് പോകുന്നത്, സിഗ്നൽ പോയാൽ?")
    assert ML.search(out["reply"]) and "മിനിറ്റ്" in out["reply"]


def test_community_question_in_malayalam_never_quotes_other_people(client):
    _, headers = register(client, name="Biju", language="ml")
    _, other = register(client, name="Selvan")
    client.post("/community/messages", headers=other, json={"text": "Big shoal near the harbour mouth, SAFE all week!"})
    out = say_ml(client, headers, "ഹാർബറിൽ മത്സ്യത്തൊഴിലാളികൾ എന്താണ് പറയുന്നത്? ചാറ്റ്")
    assert "shoal" not in out["reply"] and "SAFE all week" not in out["reply"]


def test_forecast_hour_in_malayalam(client):
    _, headers = register(client, language="ml")
    forecast.set_scenario("storm")
    out = say_ml(client, headers, "നാളെ രാവിലെ 6 മണിക്ക് പോകാമോ?")
    assert "അപകടം" in out["reply"] and not LATIN_VERDICT.search(out["reply"]) and out["proposal"] is None


def test_end_and_extend_in_malayalam(client):
    from datetime import timedelta as td

    from app.db import utcnow
    from tests.test_api import MUTHALAPOZHI
    _, headers = register(client, language="ml")
    planned = (utcnow() + td(hours=3)).isoformat() + "Z"
    trip = client.post("/trips/start", headers=headers, json={"planned_return": planned, **MUTHALAPOZHI}).json()
    out = say_ml(client, headers, "കുറച്ച് കൂടുതൽ സമയം വേണം, ഒരു മണിക്കൂർ")
    assert "1 മണിക്കൂർ" in out["reply"]
    ask = say_ml(client, headers, "ഞാൻ തിരിച്ചെത്തി")
    assert ML.search(ask["reply"]) and client.get(f"/trips/{trip['id']}", headers=headers).json()["status"] == "active"
    say_ml(client, headers, "ശരി")
    assert client.get(f"/trips/{trip['id']}", headers=headers).json()["status"] == "returned"


# ---- parsing --------------------------------------------------------------------------------

def test_parse_hours_malayalam_words_and_evening():
    assert assistant.parse_hours("രാവിലെ അഞ്ച് മണിക്ക് പോയി പതിനൊന്ന് മണിക്ക് വരും") == [5, 11]
    assert assistant.parse_hours("5 മണി മുതൽ 11 മണി വരെ") == [5, 11]
    assert assistant.parse_hours("വൈകിട്ട് 4 മണിക്ക് പോകാമോ") == [16]
    assert assistant.parse_hours("leave at 5 am, back by 11") == [5, 11]


def test_malayalam_day_and_period_words():
    fri = datetime(2026, 11, 13, 9, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert tools.detect_day_index("നാളെ രാവിലെ", fri, 7) == 1
    assert tools.detect_period("നാളെ ഉച്ചകഴിഞ്ഞ് തിര എങ്ങനെ") == "afternoon"


# ---- the model path keeps the engine's verdicts in Malayalam too ---------------------------------

def test_model_malayalam_reply_cannot_change_the_verdict(client, monkeypatch):
    _, headers = register(client, language="ml")
    forecast.set_scenario("storm")
    replies, sent = [], []
    _fake_model(monkeypatch, replies, sent)
    replies.append(json.dumps({"reply": "ഇന്ന് കടൽ സുരക്ഷിതം, പോകാം!", "action": {"type": "none"}}))
    out = say_ml(client, headers, "ഇന്ന് പോകാമോ?")
    assert out["source"] == "rules" and "പോകാം!" not in out["reply"] and "സുരക്ഷിതം" not in out["reply"]
    # the model was told the language and the Malayalam verdict words
    assert '"reply_language": "Malayalam"' in sent[0][-1]["content"] and "സുരക്ഷിതം" in sent[0][-1]["content"]


def test_model_malayalam_reply_that_matches_the_engine_is_used(client, monkeypatch):
    _, headers = register(client, language="ml")
    forecast.set_scenario("storm")
    replies, sent = [], []
    _fake_model(monkeypatch, replies, sent)
    replies.append(json.dumps({"reply": "ഇന്ന് കടൽ അപകടമാണ്, പോകരുത്.", "action": {"type": "none"}}))
    out = say_ml(client, headers, "ഇന്ന് പോകാമോ?")
    assert out["source"] == "ai" and out["reply"] == "ഇന്ന് കടൽ അപകടമാണ്, പോകരുത്."


# ---- go / no-go: windows come only from the engine -------------------------------------------------

def test_worsening_day_says_go_early_and_avoid_later(client):
    _, headers = register(client)
    forecast.set_scenario("worsening")
    with Session(engine) as s:
        ctx = asyncio.run(advisor.compute(s, 8.63, 76.78, "non_motorised", days=assistant.FORECAST_DAYS))
    for lang in ("en", "ml"):
        plan = tools.day_plan(ctx, 1, None, lang)
        spoken = tools.plan_spoken(plan, lang)
        w = ctx["days"][1]["window"]
        if w is None:
            assert plan["best_window"] is None and plan["offer"] is None
            continue
        assert plan["best_window"]["leave_from"] == tools.tx.fmt_time(w["start"], lang)
        assert spoken
        if plan["offer"]:
            for hour in range(plan["offer"]["depart_hour"], plan["offer"]["return_hour"]):
                d = ctx["dates"][1]
                assert next(h.level for h in ctx["hours"] if h.time.date() == d and h.time.hour == hour) == risk_engine.SAFE


# ---- local time -------------------------------------------------------------------------------------

class _Frozen(datetime):
    """datetime whose now() is a fixed instant: 10:40 in India (05:10 UTC)."""
    INSTANT = datetime(2026, 11, 13, 5, 10, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.INSTANT.astimezone(tz) if tz else cls.INSTANT


def test_window_starts_at_local_now_not_utc_or_a_later_hour(client, monkeypatch):
    """At 10:40 local the advice starts at 10:40 / 11 AM, never 5 AM (UTC) or 12:09, and the hours
    ahead are daytime, so the 'it is dark' reason cannot be given for them."""
    uid, headers = register(client)
    forecast.set_scenario("calm")
    monkeypatch.setattr(advisor, "datetime", _Frozen)
    with Session(engine) as s:
        me = s.get(User, uid)
        ctx = asyncio.run(advisor.compute(s, me.home_lat, me.home_lon, me.boat_type, days=assistant.FORECAST_DAYS))
    assert (ctx["now"].hour, ctx["now"].minute) == (10, 40)
    assert ctx["tz"].utcoffset(None) == timedelta(hours=5, minutes=30)
    plan = tools.day_plan(ctx, 0)
    assert plan["best_window"]["leave_from"] == "10:40 AM"
    assert plan["offer"]["depart_hour"] == 11 and plan["offer"]["depart_label"] == "11 AM"
    assert all(h["hour"] >= 10 for h in plan["hours"])  # hours already over are not offered
    today = ctx["dates"][0]
    for h in ctx["hours"]:
        if h.time.date() == today and 10 <= h.time.hour < 18:
            assert h.is_day and all(r.factor != "night" for r in h.reasons)
    facts = assistant._engine_facts(ctx, None, "en")
    assert facts["local_time_now"].endswith("10:40")
    assert facts["days"][0]["safe_window"]["from"] == "10:40 AM"
