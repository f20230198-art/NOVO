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

    alerts = client.get("/alerts", params={"user_id": user_id}).json()
    overdue = [a for a in alerts if a["kind"] == "overdue"]
    assert len(overdue) == 2  # one to the contact, one to the fisher
    to_contact = next(a for a in overdue if "Mary" in a["recipient"])
    assert to_contact["channel"] == "simulated"
    assert "Biju has not returned" in to_contact["message"]
    assert "https://maps.google.com/?q=8.60000,76.70000" in to_contact["message"]
    assert any(a["kind"] == "overdue" for a in client.get("/alerts/recent").json())

    # Sent once only
    asyncio.run(monitor.tick())
    again = [a for a in client.get("/alerts", headers=headers).json() if a["kind"] == "overdue"]
    assert len(again) == 2

    # The dashboard sees the boat, and "I'm back" closes the trip
    boats = client.get("/dashboard/trips").json()
    assert any(b["id"] == trip["id"] and b["status"] == "overdue" for b in boats)
    assert client.post(f"/trips/{trip['id']}/end", headers=headers).json()["status"] == "returned"
    assert client.get("/trips/active", headers=headers).json()["trip"] is None


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
    assert client.post("/reports", json={"type": "sea_monster", **MUTHALAPOZHI}).status_code == 422

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

    # The report feeds the risk engine: calm sea, big boat, but now CAUTION for the hours it covers.
    fc = client.get("/advisor/forecast", headers=headers).json()
    assert fc["current"]["level"] == "CAUTION"
    assert any(r["factor"] == "community_reports" for r in fc["current"]["reasons"])
    assert len(fc["reports_nearby"]) == 1
    assert fc["days"][2]["verdict"] == "SAFE"  # expired long before the day after tomorrow

    # Votes: one down-vote stops it counting towards risk; three hide it.
    assert client.post(f"/reports/{report['id']}/vote", json={"dir": "up"}).json()["up"] == 1
    for _ in range(4):
        last = client.post(f"/reports/{report['id']}/vote", json={"dir": "down"}).json()
    assert last["down"] == 4 and last["hidden"] is True
    assert client.get("/reports", params=MUTHALAPOZHI).json() == []
    assert client.get("/advisor/forecast", headers=headers).json()["current"]["level"] == "SAFE"
    assert client.post("/reports/999999/vote", json={"dir": "up"}).status_code == 404

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
    boats = client.get("/dashboard/trips").json()
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
