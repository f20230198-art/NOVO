"""Family phone linking and alert delivery, weather simulation and injections."""
import asyncio
from datetime import timedelta

import pytest

from app.db import utcnow
from app.routers import family as family_router
from app.services import monitor
from tests.test_api import MUTHALAPOZHI, client, register  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def _fresh_limits():
    family_router.link_limiter.reset()
    yield


def link_family(client, headers):
    contacts = client.get("/users/me/contacts", headers=headers).json()
    code = contacts[0]["link_code"]
    assert code and len(code) == 6 and contacts[0]["family_app"] is False
    linked = client.post("/family/link", json={"code": code}).json()
    assert linked["fisher"]["name"] == "Biju" and linked["contact"]["name"] == "Mary"
    assert client.get("/users/me/contacts", headers=headers).json()[0]["family_app"] is True
    return {"X-Family-Token": linked["token"]}


def test_family_phone_receives_sos_overdue_and_all_clear(client):
    _, headers = register(client)
    fam = link_family(client, headers)
    assert client.get("/family/messages", headers=fam).json() == []
    assert client.get("/family/messages").status_code == 401

    # Fisher presses SOS: the family phone gets it.
    client.post("/trips/sos", headers=headers, json={"lat": 8.6, "lon": 76.7, "fix": "gps"})
    msgs = client.get("/family/messages", headers=fam).json()
    assert len(msgs) == 1 and msgs[0]["kind"] == "sos" and msgs[0]["urgent"] and "maps.google.com" in msgs[0]["text"]
    # Delivered to the app, so not "simulated" in the alert log.
    alerts = client.get("/alerts", headers=headers).json()
    assert any(a["kind"] == "sos" and a["channel"] == "message" for a in alerts)
    assert not any(a["kind"] == "sos" and a["channel"] == "simulated" for a in alerts)

    # "I'm back" sends the all-clear; only new messages after the last id.
    trip = client.get("/trips/active", headers=headers).json()["trip"]
    client.post(f"/trips/{trip['id']}/end", headers=headers)
    newer = client.get("/family/messages", headers=fam, params={"after_id": msgs[0]["id"]}).json()
    assert [m["kind"] for m in newer] == ["all_clear"] and newer[0]["urgent"] is False
    assert client.get("/family/me", headers=fam).json()["trip"]["status"] == "returned"


def test_family_phone_gets_overdue_and_auto_sos_but_not_fisher_messages(client):
    _, headers = register(client)
    fam = link_family(client, headers)
    planned = (utcnow() + timedelta(hours=3)).isoformat() + "Z"
    trip = client.post("/trips/start", headers=headers, json={"planned_return": planned, **MUTHALAPOZHI}).json()
    client.post(f"/trips/{trip['id']}/ping", headers=headers, json={"lat": 8.55, "lon": 76.70})
    client.post(f"/demo/trips/{trip['id']}/lose-signal")
    asyncio.run(monitor.tick())
    kinds = [m["kind"] for m in client.get("/family/messages", headers=fam).json()]
    assert "auto_sos" in kinds and "overdue" in kinds
    assert "overdue_check" not in kinds and "overdue_fisher" not in kinds  # meant for the fisher only


def test_wrong_code_and_brute_force(client):
    assert client.post("/family/link", json={"code": "000000"}).status_code == 404
    codes = [client.post("/family/link", json={"code": "111111"}).status_code for _ in range(12)]
    assert 429 in codes


def test_removing_a_contact_unlinks_the_family_phone(client):
    _, headers = register(client)
    fam = link_family(client, headers)
    cid = client.get("/users/me/contacts", headers=headers).json()[0]["id"]
    client.delete(f"/users/me/contacts/{cid}", headers=headers)
    assert client.get("/family/messages", headers=fam).status_code == 401


@pytest.mark.parametrize("mode,boat,expected", [
    ("thunderstorm", "mechanised", "UNSAFE"),
    ("heavy_rain", "motorised", "CAUTION"),
    ("strong_wind", "mechanised", "CAUTION"),
    ("high_swell", "non_motorised", "UNSAFE"),
    ("cyclone", "mechanised", "UNSAFE"),
])
def test_simulated_weather(client, mode, boat, expected):
    _, headers = register(client, boat=boat)
    assert client.post("/demo/scenario", json={"mode": mode}).json()["mode"] == mode
    assert client.get("/advisor/forecast", headers=headers).json()["days"][1]["verdict"] == expected


def test_cyclone_posts_a_warning_and_clear_removes_injections(client):
    _, headers = register(client, boat="mechanised")
    out = client.post("/demo/scenario", json={"mode": "cyclone", **MUTHALAPOZHI}).json()
    assert out["warning_id"]
    fc = client.get("/advisor/forecast", headers=headers).json()
    assert any(w["title"] == "Cyclone alert" for w in fc["warnings"])

    client.post("/demo/scenario", json={"mode": "calm"})
    client.post("/demo/inject/warning", json={"kind": "lightning", **MUTHALAPOZHI})
    rep = client.post("/demo/inject/report", json={"type": "harbour_mouth_rough", "lat": 8.636, "lon": 76.776}).json()
    assert rep["up"] >= 1  # confirmed, so it counts
    today = client.get("/advisor/forecast", headers=headers).json()
    assert len(today["warnings"]) >= 2 and any(r["id"] == rep["id"] for r in today["reports_nearby"])

    cleared = client.post("/demo/inject/clear").json()
    assert cleared["mode"] == "real" and cleared["removed"] >= 3
    client.post("/demo/scenario", json={"mode": "calm"})
    after = client.get("/advisor/forecast", headers=headers).json()
    assert after["warnings"] == [] and all(r["id"] != rep["id"] for r in after["reports_nearby"])
