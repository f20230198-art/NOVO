"""End-to-end API tests. No network: the forecast fetch is patched to fail, so the demo
scenarios run on the built-in placeholder rows, and no keys are set (see conftest.py)."""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.services import advisor, forecast, monitor

MUTHALAPOZHI = {"lat": 8.635, "lon": 76.775}
ADMIN = {"X-Admin-Key": "test-admin"}


@pytest.fixture()
def client(monkeypatch):
    init_db()

    async def no_network(lat, lon):
        raise httpx.ConnectError("network disabled in tests")

    monkeypatch.setattr(forecast, "_fetch", no_network)
    forecast.clear_cache()
    forecast.set_scenario("calm")
    yield TestClient(app)
    forecast.set_scenario("real")


def register(client, boat="non_motorised", language="en", name="Biju"):
    resp = client.post(
        "/users",
        json={
            "name": name, "phone": "+919999900001", "language": language, "boat_type": boat,
            "home_lat": MUTHALAPOZHI["lat"], "home_lon": MUTHALAPOZHI["lon"], "home_name": "Muthalapozhi",
            "contacts": [{"name": "Mary", "phone": "+919999900002", "relation": "wife"}],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body["user_id"], {"X-User-Token": body["token"]}


def test_health_and_no_keys(client):
    body = client.get("/health").json()
    assert body["ok"] is True and body["ai"] is False and body["sms"] is False


def test_users_and_contacts(client):
    user_id, headers = register(client)
    assert client.get("/users/me").status_code == 401
    assert client.get("/users/me", headers=headers).json()["id"] == user_id

    updated = client.put("/users/me", headers=headers, json={"boat_type": "mechanised", "language": "ml"}).json()
    assert updated["boat_type"] == "mechanised" and updated["language"] == "ml"
    assert client.put("/users/me", headers=headers, json={"boat_type": "submarine"}).status_code == 422

    contact = client.post("/users/me/contacts", headers=headers, json={"name": "Co-op", "phone": "+91471000", "relation": "co-op"}).json()
    assert len(client.get("/users/me/contacts", headers=headers).json()) == 2
    assert client.delete(f"/users/me/contacts/{contact['id']}", headers=headers).json()["ok"] is True
    assert len(client.get("/users/me/contacts", headers=headers).json()) == 1


def test_full_trip_flow_register_ask_start_overdue(client):
    user_id, headers = register(client)

    # Ask (template mode: no API key)
    ask = client.post("/advisor/ask", headers=headers, json={"question": "Can I go out tomorrow morning?"}).json()
    assert ask["source"] == "template"
    assert ask["day_index"] == 1
    assert ask["verdict"] == "SAFE" and ask["window"] is not None and ask["return_by"]
    assert "SAFE" in ask["answer"] and "Advisory only" in ask["answer"]
    assert len(ask["hourly"]) == 72 and len(ask["days"]) == 3
    assert ask["confidence"] in ("high", "medium", "low")

    # Start a trip returning in 3 hours
    planned = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    trip = client.post("/trips/start", headers=headers, json={"planned_return": planned, **MUTHALAPOZHI}).json()
    assert trip["status"] == "active" and len(trip["forecast_snapshot"]) >= 3
    assert client.get("/trips/active", headers=headers).json()["trip"]["id"] == trip["id"]
    assert client.post(f"/trips/{trip['id']}/ping", headers=headers, json={"lat": 8.60, "lon": 76.70}).json()["last_lat"] == 8.60

    # Not overdue yet
    asyncio.run(monitor.tick())
    assert client.get(f"/trips/{trip['id']}", headers=headers).json()["status"] == "active"

    # Fast-forward, then one monitor tick
    assert client.post(f"/demo/trips/{trip['id']}/fast-forward").json()["ok"] is True
    result = asyncio.run(monitor.tick())
    assert result["overdue"] == 1
    assert client.get(f"/trips/{trip['id']}", headers=headers).json()["status"] == "overdue"
    alerts = client.get("/alerts", headers=headers).json()
    assert [a["kind"] for a in alerts] == ["overdue_check"]  # the fisher is asked first, the family not yet

    # After the contact delay (at most 30 min) the family is told.
    later = monitor.utcnow() + timedelta(minutes=31)
    asyncio.run(monitor.tick(now=later))
    alerts = client.get("/alerts", headers=headers).json()
    assert len([a for a in alerts if a["kind"] == "overdue_check"]) == 1
    overdue = [a for a in alerts if a["kind"] == "overdue"]
    assert len(overdue) == 2  # one to the contact, one to the fisher
    to_contact = next(a for a in overdue if "Mary" in a["recipient"])
    assert to_contact["channel"] == "simulated"
    assert "Biju has not returned" in to_contact["message"] and "Last seen at" in to_contact["message"]
    assert "https://maps.google.com/?q=8.60000,76.70000" in to_contact["message"]

    # Alerts are private: no listing another user's, and the feed needs the admin key.
    assert client.get("/alerts", params={"user_id": user_id}).status_code == 401
    assert client.get("/alerts/recent").status_code == 403
    assert any(a["kind"] == "overdue" for a in client.get("/alerts/recent", headers=ADMIN).json())

    # Sent once only
    asyncio.run(monitor.tick(now=later + timedelta(minutes=5)))
    again = [a for a in client.get("/alerts", headers=headers).json() if a["kind"] in ("overdue", "overdue_check")]
    assert len(again) == 3

    # The dashboard (admin key only) sees the boat, and "I'm back" closes the trip
    assert client.get("/dashboard/trips").status_code == 403
    boats = client.get("/dashboard/trips", headers=ADMIN).json()
    assert any(b["id"] == trip["id"] and b["status"] == "overdue" for b in boats)
    ended = client.post(f"/trips/{trip['id']}/end", headers=headers).json()
    assert ended["status"] == "returned"
    assert client.get("/trips/active", headers=headers).json()["trip"] is None

    # The family was alerted, so they are also told he is back.
    clear = [a for a in client.get("/alerts", headers=headers).json() if a["kind"] == "all_clear"]
    assert len(clear) == 1 and "back safely" in clear[0]["message"]


def test_overdue_asks_the_fisher_before_the_family(client, monkeypatch):
    from app.services import escalation

    monkeypatch.setattr(escalation, "contact_delay_minutes", lambda *args: 15)
    _, headers = register(client)
    planned = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    trip = client.post("/trips/start", headers=headers, json={"planned_return": planned, **MUTHALAPOZHI}).json()
    assert trip["contacts_alerted"] is False

    def kinds():
        return sorted(a["kind"] for a in client.get("/alerts", headers=headers).json())

    # Just overdue: only the fisher hears about it.
    client.post(f"/demo/trips/{trip['id']}/fast-forward")
    asyncio.run(monitor.tick())
    now_trip = client.get(f"/trips/{trip['id']}", headers=headers).json()
    assert now_trip["status"] == "overdue" and now_trip["contacts_alerted"] is False
    assert kinds() == ["overdue_check"]

    # "More time" answers the check: the trip is active again and nobody was worried.
    more = client.post(f"/trips/{trip['id']}/extend", headers=headers, json={"minutes": 30}).json()
    assert more["status"] == "active" and kinds() == ["overdue_check"]
    asyncio.run(monitor.tick())
    assert kinds() == ["overdue_check"]

    # No answer for longer than the delay: now the family is told.
    client.post(f"/demo/trips/{trip['id']}/fast-forward")
    asyncio.run(monitor.tick(datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=16)))
    assert kinds().count("overdue") == 2
    told = client.get(f"/trips/{trip['id']}", headers=headers).json()
    assert told["contacts_alerted"] is True
    # No SMS/Telegram key and no linked family phone: the alerts are only simulated, so the
    # app must not tell the fisher the family knows.
    assert told["contacts_reached"] is False

    # Adding time after that tells the family he is OK.
    client.post(f"/trips/{trip['id']}/extend", headers=headers, json={"minutes": 60})
    assert "extended" in kinds()
    client.post(f"/trips/{trip['id']}/end", headers=headers)


def test_storm_scenario_makes_verdict_unsafe(client):
    _, headers = register(client, boat="mechanised")
    calm = client.get("/advisor/forecast", headers=headers).json()
    assert calm["days"][0]["verdict"] in ("SAFE", "CAUTION")  # CAUTION only if run late at night
    assert calm["days"][1]["verdict"] == "SAFE"

    assert client.post("/demo/scenario", json={"mode": "storm"}).json()["mode"] == "storm"
    for boat in ("non_motorised", "motorised", "mechanised"):
        fc = client.get("/advisor/forecast", params={**MUTHALAPOZHI, "boat_type": boat}).json()
        assert [d["verdict"] for d in fc["days"]] == ["UNSAFE"] * 3
        assert all(d["window"] is None for d in fc["days"])

    ask = client.post("/advisor/ask", headers=headers, json={"question": "Can I go now?"}).json()
    assert ask["verdict"] == "UNSAFE" and "UNSAFE" in ask["answer"] and "3 m" in ask["answer"]
    assert any(r["factor"] == "weather_code" for r in ask["reasons"])
    assert client.post("/demo/scenario", json={"mode": "tsunami"}).status_code == 422


def test_boat_type_changes_the_verdict(client):
    client.post("/demo/scenario", json={"mode": "rough"})
    verdicts = {
        boat: client.get("/advisor/forecast", params={**MUTHALAPOZHI, "boat_type": boat}).json()["days"][1]["verdict"]
        for boat in ("non_motorised", "motorised", "mechanised")
    }
    assert verdicts == {"non_motorised": "UNSAFE", "motorised": "CAUTION", "mechanised": "SAFE"}


def test_malayalam_template_answer(client):
    _, headers = register(client, language="ml")
    ask = client.post("/advisor/ask", headers=headers, json={"question": "നാളെ രാവിലെ കടലിൽ പോകാമോ?"}).json()
    assert ask["day_index"] == 1 and ask["verdict"] == "SAFE"
    assert "സുരക്ഷിതം" in ask["answer"] and "1554" in ask["answer"]
    client.post("/demo/scenario", json={"mode": "storm"})
    ask = client.post("/advisor/ask", headers=headers, json={"question": "മറ്റന്നാൾ പോകാമോ?"}).json()
    assert ask["day_index"] == 2 and ask["verdict"] == "UNSAFE" and "അപകടം" in ask["answer"]


def test_reports_create_vote_expiry_and_risk(client):
    _, headers = register(client, boat="mechanised")
    voters = [register(client, name=f"Voter {i}")[1] for i in range(4)]
    assert client.post("/reports", json={"type": "debris", **MUTHALAPOZHI}).status_code == 401  # must be registered
    assert client.post("/reports", headers=headers, json={"type": "sea_monster", **MUTHALAPOZHI}).status_code == 422

    report = client.post(
        "/reports", headers=headers, json={"type": "harbour_mouth_rough", "note": "Breaking at the mouth", "anonymous": False, **MUTHALAPOZHI}
    ).json()
    created = datetime.fromisoformat(report["created_at"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(report["expires_at"].replace("Z", "+00:00"))
    assert expires - created == timedelta(hours=6)
    assert report["reporter"] == "Biju"

    nearby = client.get("/reports", params={**MUTHALAPOZHI, "radius_km": 25}).json()
    assert [r["id"] for r in nearby] == [report["id"]] and nearby[0]["distance_km"] == 0
    assert client.get("/reports", params={"lat": 25.13, "lon": 56.36}).json() == []

    # One unconfirmed report is listed and explained, but does not change the verdict.
    fc = client.get("/advisor/forecast", headers=headers).json()
    assert fc["current"]["level"] == "SAFE" and len(fc["reports_nearby"]) == 1
    assert any(r["text_key"] == "reports_unconfirmed" for r in fc["current"]["reasons"])

    # Votes need a registered fisher, not the reporter, and count once per fisher.
    vote_url = f"/reports/{report['id']}/vote"
    assert client.post(vote_url, json={"dir": "up"}).status_code == 401
    assert client.post(vote_url, headers=headers, json={"dir": "up"}).status_code == 403
    assert client.post(vote_url, headers=voters[0], json={"dir": "up"}).json()["up"] == 1
    assert client.post(vote_url, headers=voters[0], json={"dir": "up"}).json()["up"] == 1  # same vote again: no change

    # Confirmed by another fisher: calm sea, big boat, but now CAUTION for the hours it covers.
    fc = client.get("/advisor/forecast", headers=headers).json()
    assert fc["current"]["level"] == "CAUTION"
    assert any(r["factor"] == "community_reports" and r["level"] == "CAUTION" for r in fc["current"]["reasons"])
    assert fc["days"][2]["verdict"] == "SAFE"  # expired long before the day after tomorrow

    # A fisher can change their mind; it takes three more people than supporters to hide a report.
    switched = client.post(vote_url, headers=voters[0], json={"dir": "down"}).json()
    assert switched["up"] == 0 and switched["down"] == 1 and switched["hidden"] is False
    for voter in voters[1:]:
        last = client.post(vote_url, headers=voter, json={"dir": "down"}).json()
    assert last["down"] == 4 and last["hidden"] is True
    assert client.get("/reports", params=MUTHALAPOZHI).json() == []
    assert client.get("/advisor/forecast", headers=headers).json()["current"]["level"] == "SAFE"
    assert client.post("/reports/999999/vote", headers=voters[0], json={"dir": "up"}).status_code == 404

    # A call for help cannot be voted out of sight, and its position is exact.
    help_call = client.post("/reports", headers=headers, json={"type": "boat_in_trouble", "lat": 8.63512, "lon": 76.77534}).json()
    assert (help_call["lat"], help_call["lon"]) == (8.63512, 76.77534)
    for voter in voters:
        still = client.post(f"/reports/{help_call['id']}/vote", headers=voter, json={"dir": "down"}).json()
    assert still["hidden"] is False

    # Other positions are rounded so a report does not give away the reporter's fishing spot.
    catch = client.post("/reports", headers=headers, json={"type": "no_fish", "lat": 8.63512, "lon": 76.77534}).json()
    assert (catch["lat"], catch["lon"]) == (8.6, 76.8)

    # Flood limit: five reports an hour per fisher.
    spam = [client.post("/reports", headers=voters[3], json={"type": "debris", "lat": 20.0, "lon": 60.0}).status_code for _ in range(6)]
    assert spam == [200] * 5 + [429]

    # Expiry: a report whose time has passed is no longer listed.
    from sqlmodel import Session

    from app.db import engine, utcnow
    from app.services import community

    with Session(engine) as session:
        old = community.create_report(session, "debris", **MUTHALAPOZHI, now=utcnow() - timedelta(hours=13))
        fresh = community.create_report(session, "debris", **MUTHALAPOZHI, now=utcnow() - timedelta(hours=11))
        old_id, fresh_id = old.id, fresh.id
    ids = [r["id"] for r in client.get("/reports", params=MUTHALAPOZHI).json()]
    assert fresh_id in ids and old_id not in ids


def test_official_warning_needs_admin_key_and_overrides(client):
    body = {"title": "Cyclone warning", "message": "Stay ashore", "center_lat": 8.6, "center_lon": 76.8, "radius_km": 60, "hours": 100}
    assert client.post("/warnings", json=body).status_code == 403
    assert client.post("/warnings", json=body, headers={"X-Admin-Key": "wrong"}).status_code == 403
    warning = client.post("/warnings", json=body, headers={"X-Admin-Key": "test-admin"}).json()

    assert any(w["id"] == warning["id"] for w in client.get("/warnings/active", params=MUTHALAPOZHI).json())
    assert client.get("/warnings/active", params={"lat": 25.13, "lon": 56.36}).json() == []

    fc = client.get("/advisor/forecast", params={**MUTHALAPOZHI, "boat_type": "mechanised"}).json()
    assert [d["verdict"] for d in fc["days"]] == ["UNSAFE"] * 3
    assert fc["days"][0]["reasons"][0]["factor"] == "official_warning"
    assert "Cyclone warning" in fc["days"][0]["reasons"][0]["text"]
    assert client.delete(f"/warnings/{warning['id']}", headers={"X-Admin-Key": "test-admin"}).json()["ok"] is True


def test_sos_alerts_contacts(client):
    user_id, headers = register(client)
    result = client.post("/trips/sos", headers=headers, json={"lat": 8.61, "lon": 76.72}).json()
    assert result["trip"]["status"] == "emergency"
    assert result["alerts"][0]["kind"] == "sos" and result["alerts"][0]["channel"] == "simulated"
    assert "SOS from Biju" in result["alerts"][0]["message"] and "8.61000,76.72000" in result["alerts"][0]["message"]


def test_head_back_alert_in_worsening_scenario(client):
    _, headers = register(client, boat="non_motorised")
    planned = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
    trip = client.post("/trips/start", headers=headers, json={"planned_return": planned, **MUTHALAPOZHI}).json()
    asyncio.run(monitor.tick())
    assert client.get(f"/trips/{trip['id']}", headers=headers).json()["head_back"] is None

    client.post("/demo/scenario", json={"mode": "worsening"})
    asyncio.run(monitor.tick())
    asyncio.run(monitor.tick())  # second tick must not repeat the alert
    alerts = [a for a in client.get("/alerts", headers=headers).json() if a["kind"] == "head_back"]
    assert len(alerts) == 1 and alerts[0]["message"].startswith("Head back now:")
    assert client.get(f"/trips/{trip['id']}", headers=headers).json()["head_back"] is not None

    # Level drops, then rises again: re-armed, so a second alert goes out.
    client.post("/demo/scenario", json={"mode": "calm"})
    asyncio.run(monitor.tick())
    client.post("/demo/scenario", json={"mode": "storm"})
    asyncio.run(monitor.tick())
    alerts = [a for a in client.get("/alerts", headers=headers).json() if a["kind"] == "head_back"]
    assert len(alerts) == 2
    client.post(f"/trips/{trip['id']}/end", headers=headers)


def test_seed_and_dashboard(client):
    seeded = client.post("/demo/seed").json()
    assert len(seeded["users"]) == 4 and len(seeded["reports"]) == 3 and len(seeded["trips"]) == 2
    again = client.post("/demo/seed").json()  # idempotent
    assert len(again["users"]) == 4
    boats = client.get("/dashboard/trips", headers=ADMIN).json()
    assert {b["name"] for b in boats} >= {"Selvan", "Antony"}
    assert client.get("/warnings/active", params={"lat": 25.13, "lon": 56.36}).json()[0]["source"] == "Demo seed"
    page = client.get("/dashboard")
    assert page.status_code == 200 and "Sea Safe" in page.text


def test_answer_consistency_check():
    assert advisor.contradicts("Tomorrow is safe from 6 AM.", "UNSAFE", "en") is True
    assert advisor.contradicts("Tomorrow is UNSAFE. Waves reach 3 m. Do not go.", "UNSAFE", "en") is False
    assert advisor.contradicts("It is not safe tomorrow, it is dangerous.", "UNSAFE", "en") is False
    assert advisor.contradicts("Tomorrow is SAFE from 6 AM to 10 AM.", "SAFE", "en") is False
    assert advisor.contradicts("Do not go tomorrow, though it looks safe.", "SAFE", "en") is True
    assert advisor.contradicts("Take caution tomorrow.", "CAUTION", "en") is False
    assert advisor.contradicts("നാളെ കടൽ സുരക്ഷിതം.", "UNSAFE", "ml") is True
    assert advisor.contradicts("നാളെ കടലിൽ പോകുന്നത് അപകടം. കടലിൽ പോകരുത്.", "UNSAFE", "ml") is False
    assert advisor.contradicts("നാളെ സുരക്ഷിതം.", "SAFE", "ml") is False
    assert advisor.contradicts("നാളെ കടൽ സുരക്ഷിതമല്ല.", "SAFE", "ml") is True
    assert advisor.contradicts("Tomorrow is unsafe.", "SAFE", "en") is True


def test_answer_must_state_the_return_time():
    window = {"return_by": datetime(2026, 11, 13, 10, 30)}
    assert advisor.misses_return_time("Safe from 4 AM. Come back by 10:30 AM.", window) is False
    assert advisor.misses_return_time("രാവിലെ 10.30-ന് മുമ്പ് തിരിച്ചെത്തുക.", window) is False
    assert advisor.misses_return_time("Safe from 4 AM. Come back by 11:30 AM.", window) is True
    assert advisor.misses_return_time("Safe all morning.", window) is True
    assert advisor.misses_return_time("Come back by 13:30.", {"return_by": datetime(2026, 11, 13, 13, 30)}) is False
    assert advisor.misses_return_time("Come back by 1:30 PM.", {"return_by": datetime(2026, 11, 13, 13, 30)}) is False
    assert advisor.misses_return_time("Do not go.", None) is False


def test_gemini_or_groq_words_the_answer_but_never_the_verdict(client, monkeypatch):
    from app.config import settings

    _, headers = register(client)
    template = client.post("/advisor/ask", headers=headers, json={"question": "Can I go out tomorrow?"}).json()
    return_by = template["window"]["return_by_label"]
    from app.services import llm

    replies, sent = [], []

    async def fake_post(k, payload, timeout):
        sent.append((k.url, k.key, k.model))
        return {"choices": [{"message": {"content": replies.pop(0)}}]}

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(llm, "_post", fake_post)
    llm.reset_pool()
    monkeypatch.setattr(llm, "_pool", None)
    assert client.get("/health").json()["ai_provider"] == "pool"

    # A faithful answer is used as written.
    replies.append('{"day_index": 1, "start_hour": null, "answer": "Tomorrow is safe, friend. Be back by %s.", "short_answer": "Safe"}' % return_by)
    good = client.post("/advisor/ask", headers=headers, json={"question": "Can I go out tomorrow?"}).json()
    assert good["source"] == "ai" and good["answer"].startswith("Tomorrow is safe, friend") and good["verdict"] == "SAFE"
    assert "generativelanguage.googleapis.com" in sent[0][0] and sent[0][1] == "test-key" and sent[0][2] == "gemini-2.5-flash"

    # One that contradicts the engine, drops the return time, or is not JSON falls back to the template.
    for bad in (
        '{"day_index": 1, "start_hour": null, "answer": "Tomorrow is unsafe. Do not go.", "short_answer": "No"}',
        '{"day_index": 1, "start_hour": null, "answer": "Tomorrow is safe all day.", "short_answer": "Safe"}',
        "Sure! Tomorrow looks fine.",
    ):
        replies.append(bad)
        out = client.post("/advisor/ask", headers=headers, json={"question": "Can I go out tomorrow?"}).json()
        assert out["source"] == "template" and out["verdict"] == "SAFE" and out["answer"] == template["answer"]

    # Groq is used when it is the only key, and LLM_MODEL overrides the default model.
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "groq_api_key", "groq-key")
    monkeypatch.setattr(settings, "llm_model", "some-other-model")
    llm.reset_pool()
    replies.append("{}")
    client.post("/advisor/ask", headers=headers, json={"question": "Can I go out tomorrow?"})
    assert "api.groq.com" in sent[-1][0] and sent[-1][2] == "some-other-model"
    llm.reset_pool()


def test_key_pool_rotates_and_resends_the_same_context(monkeypatch):
    """Each call starts on the next key; a 429 moves the identical messages to the next key."""
    from app.services import llm

    pool = llm.KeyPool([llm.PoolKey("groq", f"k{i}", f"groq#{i}") for i in range(1, 5)])
    llm.reset_pool(pool)
    seen = []

    async def fake_post(k, payload, timeout):
        seen.append((k.label, payload["messages"]))
        if k.label == "groq#1":
            req = httpx.Request("POST", k.url)
            raise httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, request=req, headers={"retry-after": "20"}))
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    monkeypatch.setattr(llm, "_post", fake_post)
    messages = [{"role": "system", "content": "rules"}, {"role": "user", "content": "facts + question"}]
    try:
        assert asyncio.run(llm.chat_json(messages)) == {"ok": True}
        # groq#1 was rate limited, groq#2 got exactly the same conversation.
        assert [s[0] for s in seen] == ["groq#1", "groq#2"] and seen[0][1] == seen[1][1] == messages
        # Next call starts at the next key in the rotation, and #1 is now cooling down.
        seen.clear()
        asyncio.run(llm.chat_json(messages))
        assert seen[0][0] == "groq#2"
        seen.clear()
        asyncio.run(llm.chat_json(messages))
        assert seen[0][0] == "groq#3"
        assert pool.keys[0].cooldown_until > 0 and pool.status()[0]["failures"] == 1
        # Keys never appear in the status output.
        assert "k1" not in str(pool.status())
    finally:
        llm.reset_pool()


def test_old_forecast_is_not_called_safe(client):
    _, headers = register(client, boat="mechanised")
    assert client.get("/advisor/forecast", headers=headers).json()["days"][1]["verdict"] == "SAFE"

    # The same data, but it could not be refreshed for four hours.
    key = (round(MUTHALAPOZHI["lat"], 2), round(MUTHALAPOZHI["lon"], 2))
    old = forecast._synthetic(**MUTHALAPOZHI)
    old["fetched_at"] = datetime.now(timezone.utc) - timedelta(hours=4)
    forecast._cache[key] = {"at": 0, "data": old}
    fc = client.get("/advisor/forecast", headers=headers).json()
    assert fc["stale"] is True and fc["age_minutes"] >= 240
    assert fc["days"][1]["verdict"] == "CAUTION" and fc["days"][1]["window"] is None
    assert any(r["factor"] == "data_stale" for r in fc["days"][1]["reasons"])
    forecast.clear_cache()
