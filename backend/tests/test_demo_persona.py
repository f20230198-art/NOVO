"""Demo persona (Shibu, Vizhinjam) and the `kerala_week` emulated weather.

No network: the forecast fetch is patched to fail, so the scenario runs on placeholder rows.
"""
import math
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.db import engine, init_db
from app.main import app
from app.models import (Buddy, ChatMessage, CommunityEvent, Contact, EventRsvp, Report, Trip, User, Vote,
                        Warning)
from app.services import demo_persona, demo_weather, forecast, risk_engine
from app.thresholds import THRESHOLDS

ADMIN = {"X-Admin-Key": "test-admin"}
VIZHINJAM_SEA = (8.37, 76.95)


@pytest.fixture()
def client(monkeypatch):
    init_db()

    async def no_network(lat, lon):
        raise httpx.ConnectError("network disabled in tests")

    monkeypatch.setattr(forecast, "_fetch", no_network)
    forecast.clear_cache()
    forecast.set_scenario("calm")
    c = TestClient(app)
    yield c
    c.delete("/demo/persona", headers=ADMIN)  # never leak the persona into other tests
    forecast.set_scenario("real")


def _counts() -> dict:
    with Session(engine) as s:
        ids = [u.id for u in s.exec(select(User).where(User.phone.startswith(demo_persona.PHONE_PREFIX))).all()]
        def n(model, col):
            return len(s.exec(select(model).where(col.in_(ids))).all()) if ids else 0
        return {
            "users": len(ids),
            "contacts": n(Contact, Contact.user_id),
            "trips": n(Trip, Trip.user_id),
            "reports": n(Report, Report.user_id),
            "votes": n(Vote, Vote.user_id),
            "chat": n(ChatMessage, ChatMessage.user_id),
            "events": n(CommunityEvent, CommunityEvent.created_by),
            "rsvps": n(EventRsvp, EventRsvp.user_id),
            "buddies": n(Buddy, Buddy.user_id),
            "tracks": len(s.exec(select(demo_persona.DemoTrackPoint)).all()),
            "warnings": len(s.exec(select(Warning).where(Warning.source == demo_persona.WARNING_SOURCE)).all()),
        }


# ---- emulated weather ------------------------------------------------------------

def _week(lat, lon, anchor):
    return [demo_weather.values_at(lat, lon, anchor + timedelta(hours=h), anchor) for h in range(7 * 24)]


def test_scenario_values_are_valid_everywhere():
    anchor = datetime(2026, 11, 13, 5, tzinfo=timezone.utc)
    points = demo_weather.grid_points()
    assert len(points) >= 30
    for lat, lon in points[::3]:
        for v in _week(lat, lon, anchor):
            for key in ("wave_height", "wave_period", "wind_wave_height", "swell_wave_height", "wind_speed", "wind_gust",
                        "precipitation", "current_speed", "sea_level"):
                assert math.isfinite(v[key]), key
            assert 0 < v["wave_height"] < 6 and 4 <= v["wave_period"] <= 14
            assert v["wave_height"] >= max(v["swell_wave_height"], v["wind_wave_height"]) * 0.9
            assert 0 <= v["wind_speed"] <= v["wind_gust"] < 110
            assert v["precipitation"] >= 0 and v["current_speed"] >= 0 and abs(v["sea_level"]) < 1
            for key in ("wind_dir", "wave_direction", "current_dir"):
                assert 0 <= v[key] <= 360
            assert v["weather_code"] in (1, 2, 3, 61, 63, 80, 95)
            assert v["is_day"] in (0, 1)


def test_scenario_is_deterministic_and_land_is_dropped():
    anchor = datetime(2026, 11, 13, 5, tzinfo=timezone.utc)
    t = anchor + timedelta(hours=40)
    assert demo_weather.values_at(8.3, 76.9, t, anchor) == demo_weather.values_at(8.3, 76.9, t, anchor)
    assert demo_weather.is_sea(8.37, 76.95) and not demo_weather.is_sea(8.5, 77.0)  # Thiruvananthapuram city
    grid = {"times": [t], "points": [{"lat": 8.37, "lon": 76.95, "wave": [None], "wave_dir": [None], "wind": [None],
                                      "wind_dir": [None]},
                                     {"lat": 8.50, "lon": 77.00, "wave": [None], "wave_dir": [None], "wind": [None],
                                      "wind_dir": [None]}]}
    out = demo_weather.apply_to_grid(grid, anchor)
    assert [(p["lat"], p["lon"]) for p in out["points"]] == [(8.37, 76.95)]
    assert out["points"][0]["wave"][0] > 1.5 and out["points"][0]["wind_dir"][0] is not None


def test_scenario_story_calm_then_rough_then_swell():
    anchor = datetime(2026, 11, 13, 5, tzinfo=timezone.utc)
    week = _week(*VIZHINJAM_SEA, anchor)
    first_day, peak, swell_day = week[:24], week[38:54], week[76:96]
    assert max(v["wave_height"] for v in first_day) < 1.0 and max(v["wind_speed"] for v in first_day) < 30
    assert min(v["wind_speed"] for v in peak) >= 40 and max(v["wave_height"] for v in peak) >= 2.3
    assert any(v["weather_code"] == 95 for v in week[30:60])
    assert min(v["wave_period"] for v in swell_day) >= 10  # long leftover swell: the bar gets worse than the sea
    # Rougher offshore than close in, and rougher towards Kanyakumari than up at Muthalapozhi.
    t = anchor + timedelta(hours=44)
    near, far = demo_weather.values_at(8.36, 76.97, t, anchor), demo_weather.values_at(8.25, 76.75, t, anchor)
    south, north = demo_weather.values_at(8.15, 77.2, t, anchor), demo_weather.values_at(8.62, 76.7, t, anchor)
    assert far["wave_height"] > near["wave_height"] and south["wind_speed"] > north["wind_speed"]


def test_engine_verdicts_follow_the_story():
    """The verdict still comes only from risk_engine, applied to the emulated rows."""
    anchor = datetime(2026, 11, 13, 5, tzinfo=timezone.utc)
    rows = [{"time": anchor + timedelta(hours=h), "is_day": 1} for h in range(7 * 24)]
    rows = forecast.apply_scenario(rows, demo_weather.MODE, anchor, *VIZHINJAM_SEA)
    levels = [risk_engine.evaluate_range([r], "motorised", THRESHOLDS)[0].level for r in rows]
    assert "UNSAFE" not in levels[:24]
    assert all(lv == "UNSAFE" for lv in levels[40:52])
    assert levels[130:150].count("SAFE") > 15


# ---- seeding -----------------------------------------------------------------------

def test_load_needs_the_admin_key(client):
    assert client.post("/demo/persona").status_code == 403
    assert client.delete("/demo/persona").status_code == 403
    assert client.post("/demo/persona/adopt").status_code == 404  # not loaded yet
    assert client.get("/demo/persona").json()["loaded"] is False


def test_load_is_idempotent_and_reset_is_clean(client):
    first = client.post("/demo/persona", headers=ADMIN).json()
    assert first["scenario"] == "kerala_week" and first["persona"]["demo"] is True
    counts = _counts()
    assert counts == {"users": 6, "contacts": 7, "trips": 5, "reports": 5, "votes": 3, "chat": 8, "events": 3,
                      "rsvps": 9, "buddies": 6, "tracks": counts["tracks"], "warnings": 1}
    assert counts["tracks"] > 100

    second = client.post("/demo/persona", headers=ADMIN).json()
    assert _counts() == counts
    assert second["persona"]["profile"]["token"] == first["persona"]["profile"]["token"]  # an adopted phone stays Shibu

    # Rows the fisher made on stage are cleared by a reload too.
    headers = {"X-User-Token": second["persona"]["profile"]["token"]}
    client.post("/reports", headers=headers, json={"type": "debris", "lat": 8.36, "lon": 76.96})
    client.post("/demo/persona", headers=ADMIN)
    assert _counts() == counts

    cleared = client.delete("/demo/persona", headers=ADMIN).json()
    assert cleared["removed_users"] == 6 and cleared["scenario"] == "real"
    assert all(v == 0 for v in _counts().values())


def test_phone_numbers_are_fake_and_warning_is_labelled(client):
    client.post("/demo/persona", headers=ADMIN)
    with Session(engine) as s:
        users = s.exec(select(User).where(User.phone.startswith(demo_persona.PHONE_PREFIX))).all()
        ids = [u.id for u in users]
        contacts = s.exec(select(Contact).where(Contact.user_id.in_(ids))).all()
        for phone in [u.phone for u in users] + [c.phone for c in contacts]:
            assert phone.startswith("+9190000000") and len(phone) == 13
        w = s.exec(select(Warning).where(Warning.source == demo_persona.WARNING_SOURCE)).one()
        assert "demo" in w.title.lower() and "not an official" in w.message.lower()


def test_adopted_persona_sees_the_week_with_reports_and_warning(client):
    persona = client.post("/demo/persona", headers=ADMIN).json()["persona"]
    adopted = client.post("/demo/persona/adopt").json()
    assert adopted["profile"]["token"] == persona["profile"]["token"]
    assert adopted["profile"]["home_name"] == "Vizhinjam" and adopted["profile"]["boat_type"] == "motorised"
    assert {c["relation"] for c in adopted["contacts"]} == {"wife", "brother"}
    headers = {"X-User-Token": adopted["profile"]["token"]}

    fc = client.get("/advisor/forecast", headers=headers, params={"days": 3}).json()
    assert fc["scenario"] == "kerala_week"  # the app's demo banner
    verdicts = [d["verdict"] for d in fc["days"]]
    assert verdicts[0] != "UNSAFE" and "UNSAFE" in verdicts[1:]
    assert any(w["source"] == demo_persona.WARNING_SOURCE for w in fc["warnings"])
    types = {r["type"] for r in fc["reports_nearby"]}
    assert "harbour_mouth_rough" in types

    def report_caution_hours():
        hourly = client.get("/advisor/forecast", headers=headers, params={"days": 1}).json()["hourly"]
        return sum(1 for h in hourly for r in h["reasons"] if r["factor"] == "community_reports" and r["level"] == "CAUTION")

    # Rule 2: the harbour-mouth report is unconfirmed, so it changes nothing until another fisher confirms it.
    # Other tests share this database, so drop reports that are not the persona world's first.
    with Session(engine) as s:
        ids = [u.id for u in s.exec(select(User).where(User.phone.startswith(demo_persona.PHONE_PREFIX))).all()]
        for r in s.exec(select(Report)).all():
            if r.user_id not in ids:
                s.delete(r)
        s.commit()
    assert report_caution_hours() == 0
    mouth = next(r for r in fc["reports_nearby"] if r["type"] == "harbour_mouth_rough")
    client.post(f"/reports/{mouth['id']}/vote", headers=headers, json={"dir": "up"})
    assert report_caution_hours() > 0


def test_tracks_and_buddies_respect_privacy(client):
    persona = client.post("/demo/persona", headers=ADMIN).json()["persona"]
    headers = {"X-User-Token": persona["profile"]["token"]}
    assert client.get("/demo/persona/trips").status_code == 401
    status = client.get("/demo/persona").json()
    assert status["loaded"] is True and "token" not in str(status) and "phone" not in status

    trips = client.get("/demo/persona/trips", headers=headers).json()
    assert len(trips) == 4 and all(t["status"] == "returned" for t in trips)
    home = (persona["profile"]["home_lat"], persona["profile"]["home_lon"])
    for t in trips:
        track = t["track"]
        assert len(track) > 20
        assert (track[0]["lat"], track[0]["lon"]) == home == (track[-1]["lat"], track[-1]["lon"])
        assert all(demo_weather.is_sea(p["lat"], p["lon"]) for p in track[1:-1])
        assert 10 <= t["max_offshore_km"] <= 30

    buddies = client.get("/buddies", headers=headers).json()
    by_name = {b["name"]: b for b in buddies}
    assert set(by_name) == {"Mani Perera", "Lawrence D'Cruz"}
    assert by_name["Mani Perera"]["status"] == "active" and by_name["Mani Perera"]["lat"] is None  # at sea, private


def _has_malayalam(text: str) -> bool:
    return any("ഀ" <= ch <= "ൿ" for ch in text or "")


def test_persona_loads_in_malayalam(client):
    loaded = client.post("/demo/persona", headers=ADMIN, json={"language": "ml"}).json()
    assert loaded["persona"]["profile"]["language"] == "ml" and _has_malayalam(loaded["persona"]["boat"])
    adopted = client.post("/demo/persona/adopt").json()
    assert adopted["profile"]["language"] == "ml"
    headers = {"X-User-Token": adopted["profile"]["token"]}

    # The server's own text comes back in Malayalam through the existing template path.
    fc = client.get("/advisor/forecast", headers=headers, params={"days": 3}).json()
    assert fc["language"] == "ml" and all(_has_malayalam(d["verdict_word"]) for d in fc["days"])
    texts = [r["text"] for h in fc["hourly"] for r in h["reasons"]]
    assert texts and all(_has_malayalam(t) for t in texts)
    assert any(t.startswith("ഔദ്യോഗിക") for t in texts)  # the sample warning, in the rough spell

    # The sample warning carries both languages.
    w = next(w for w in fc["warnings"] if w["source"] == demo_persona.WARNING_SOURCE)
    for field in ("title", "message"):
        assert _has_malayalam(w[field]) and any("a" <= ch.lower() <= "z" for ch in w[field])

    # The harbour writes in both languages, as it would in Vizhinjam.
    chat = client.get("/community/messages", headers=headers, params={"channel": "harbour"}).json()
    assert sum(_has_malayalam(m["text"]) for m in chat) >= 4 and sum(not _has_malayalam(m["text"]) for m in chat) >= 2
    notes = [r["note"] for r in fc["reports_nearby"]]
    assert any(_has_malayalam(n) for n in notes)
    events = client.get("/community/events", headers=headers).json()
    assert any(_has_malayalam(e["title"]) for e in events) and any(not _has_malayalam(e["title"]) for e in events)

    # Reloading in English switches Shibu back, same token.
    again = client.post("/demo/persona", headers=ADMIN, json={"language": "en"}).json()
    assert again["persona"]["profile"]["language"] == "en" and not _has_malayalam(again["persona"]["boat"])
    assert again["persona"]["profile"]["token"] == adopted["profile"]["token"]
    assert client.post("/demo/persona", headers=ADMIN, json={"language": "ta"}).status_code == 422


def test_demo_panel_labels_have_malayalam():
    """Every scenario label and the demo-fisher chip in en.ts must have a Malayalam entry in ml.ts."""
    import pathlib
    import re

    i18n = pathlib.Path(__file__).resolve().parents[2] / "mobile" / "src" / "i18n"
    if not i18n.exists():
        pytest.skip("mobile app not next to the backend")
    keys = lambda f: set(re.findall(r"^\s+(\w+):", (i18n / f).read_text(encoding="utf-8"), re.M))  # noqa: E731
    en, ml = keys("en.ts"), keys("ml.ts")
    wanted = {k for k in en if k.startswith("sim_")} | {"demoFisher", "demoFisherDone", "demoBanner"}
    assert f"sim_{demo_weather.MODE}" in en
    assert wanted - ml == set()


def test_old_seed_and_persona_coexist(client):
    client.post("/demo/persona", headers=ADMIN)
    before = _counts()
    assert len(client.post("/demo/seed").json()["users"]) == 4
    assert _counts() == before
    client.post("/demo/persona", headers=ADMIN)
    assert len(client.get("/warnings/active", params={"lat": 25.13, "lon": 56.36}).json()) >= 1  # seed warning kept
