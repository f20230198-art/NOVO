"""Drift search zone, harbour-mouth crossing, buddy boats and ask-by-SMS."""
import asyncio
from datetime import date, datetime, timedelta, timezone

from app.services import drift, forecast, monitor
from app.services import risk_engine as re
from app.services.risk_engine import CAUTION, SAFE, UNSAFE
from app.thresholds import THRESHOLDS as TH

from .test_api import ADMIN, MUTHALAPOZHI, client, register  # noqa: F401  (client is a fixture)

IST = timezone(timedelta(hours=5, minutes=30))
DAY = date(2026, 11, 12)
CFG = TH["drift"]


def rows(hours=24, **values):
    base = {"wave_height": 0.4, "wave_period": 6.0, "wind_speed": 0.0, "wind_dir": 0.0,
            "current_speed": 0.0, "current_dir": 0.0, "sea_level": 0.0}
    base.update(values)
    return [{**base, "time": datetime(2026, 11, 12, 0, tzinfo=IST) + timedelta(hours=h)} for h in range(hours)]


def at(hour, minute=0):
    return datetime(2026, 11, 12, hour, minute, tzinfo=IST)


# ---- drift ------------------------------------------------------------------------------

def test_no_current_and_no_wind_stays_put_but_the_search_radius_still_grows():
    zone = drift.predict(8.6, 76.7, at(6), at(8), rows(), CFG)
    now, later = zone["points"][0], zone["points"][-1]
    assert (now["lat"], now["lon"]) == (8.6, 76.7)
    assert later["radius_km"] > now["radius_km"] > CFG["base_radius_km"]


def test_current_carries_the_boat_the_way_the_water_flows():
    # 2 km/h flowing east for 3 hours is about 6 km east.
    zone = drift.predict(8.6, 76.7, at(6), at(9), rows(current_speed=2.0, current_dir=90.0), CFG)
    p = zone["points"][0]
    east_km = (p["lon"] - 76.7) * drift.KM_PER_DEG_LON * 0.9887
    assert abs(east_km - 6.0) < 0.2 and abs(p["lat"] - 8.6) < 1e-3
    assert zone["basis"] == "current+wind" and zone["heading_deg"] == 90


def test_wind_from_the_north_pushes_the_boat_south():
    zone = drift.predict(8.6, 76.7, at(6), at(10), rows(wind_speed=40.0, wind_dir=0.0), CFG)
    p = zone["points"][0]
    south_km = (8.6 - p["lat"]) * drift.KM_PER_DEG_LAT
    assert abs(south_km - 0.03 * 40 * 4) < 0.1


def test_drift_without_any_data_says_so():
    empty = [{"time": at(h)} for h in range(24)]
    zone = drift.predict(8.6, 76.7, at(6), at(8), empty, CFG)
    assert zone["basis"] == "none" and zone["points"][0]["lat"] == 8.6


def test_points_cover_now_and_the_hours_ahead():
    zone = drift.predict(8.6, 76.7, at(6), at(8), rows(current_speed=1.0, current_dir=180.0), CFG)
    assert [p["hours_ahead"] for p in zone["points"]] == [0, 1, 3, 6]
    lats = [p["lat"] for p in zone["points"]]
    assert lats == sorted(lats, reverse=True)  # keeps going south


# ---- harbour mouth ----------------------------------------------------------------------

def bar(boat="non_motorised", prev=None, **values):
    r = rows(1, **values)[0]
    return re.bar_hour(r, boat, TH, prev)


def test_short_small_sea_is_safe_to_cross():
    assert bar(wave_height=0.5, wave_period=5.0)["level"] == SAFE


def test_long_swell_breaks_at_the_bar_though_the_open_sea_is_fine():
    # 0.9 m is under the open-sea caution limit for a canoe, but an 11 s swell stands up on the bar.
    open_sea = re.evaluate_hour({**rows(1, wave_height=0.9, wave_period=11.0)[0], "is_day": 1}, "non_motorised", TH)
    crossing = bar(wave_height=0.9, wave_period=11.0)
    assert open_sea.level == SAFE and crossing["level"] == CAUTION and crossing["long_swell"]


def test_falling_tide_makes_the_same_swell_worse():
    before = {"sea_level": 0.4}
    flood = bar("motorised", prev={"sea_level": -0.2}, wave_height=1.0, wave_period=10.0, sea_level=0.0)
    ebb = bar("motorised", prev=before, wave_height=1.0, wave_period=10.0, sea_level=0.0)
    assert not flood["ebb"] and ebb["ebb"]
    assert ebb["breaker_m"] > flood["breaker_m"]
    assert flood["level"] == SAFE and ebb["level"] == CAUTION


def test_bigger_boats_cross_what_small_boats_cannot():
    kw = dict(wave_height=1.3, wave_period=10.0)
    assert bar("non_motorised", **kw)["level"] == UNSAFE
    assert bar("motorised", **kw)["level"] == CAUTION
    assert bar("mechanised", **kw)["level"] == SAFE


def test_missing_wave_data_is_never_a_safe_crossing():
    assert bar(wave_height=None)["level"] == CAUTION


def test_crossing_windows_are_the_safe_runs():
    data = rows(24, wave_height=0.5, wave_period=5.0)
    for r in data:
        if 9 <= r["time"].hour < 12:
            r["wave_height"], r["wave_period"] = 1.4, 12.0
    windows = re.bar_windows(re.bar_range(data, "non_motorised", TH), DAY)
    assert [(w["start"].hour, w["end"].hour) for w in windows] == [(3, 9), (12, 19)]


def test_forecast_carries_the_harbour_mouth(client):  # noqa: F811
    _, headers = register(client)
    body = client.get("/advisor/forecast", headers=headers).json()
    mouth = body["harbour_mouth"]
    assert mouth["level"] in (SAFE, CAUTION, UNSAFE)
    assert len(mouth["days"]) == 3 and len(mouth["hourly"]) == len(body["hourly"])


# ---- dashboard drift, buddies, sms ------------------------------------------------------

def _second(client, name="Selvan", phone="+919999900055"):  # noqa: F811
    resp = client.post("/users", json={
        "name": name, "phone": phone, "language": "en", "boat_type": "motorised",
        "home_lat": MUTHALAPOZHI["lat"], "home_lon": MUTHALAPOZHI["lon"], "home_name": "Muthalapozhi", "contacts": [],
    })
    body = resp.json()
    return body["user_id"], {"X-User-Token": body["token"]}


def test_overdue_boat_gets_a_search_zone_and_its_buddy_is_told(client):  # noqa: F811
    _, biju = register(client)
    _, selvan = _second(client)
    assert client.post("/buddies", json={"phone": "99999 00055"}, headers=biju).status_code == 200
    assert [b["name"] for b in client.get("/buddies", headers=selvan).json()] == ["Biju"]

    back = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    trip = client.post("/trips/start", json={"planned_return": back, **MUTHALAPOZHI}, headers=biju).json()
    # An active trip has no search zone and its position stays private from the buddy.
    out = [t for t in client.get("/dashboard/trips", headers=ADMIN).json() if t["id"] == trip["id"]][0]
    assert out["drift"] is None
    assert client.get("/buddies", headers=selvan).json()[0]["lat"] is None

    asyncio.run(monitor.tick(datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=4)))
    out = [t for t in client.get("/dashboard/trips", headers=ADMIN).json() if t["id"] == trip["id"]][0]
    assert out["status"] in ("overdue", "emergency")  # four hours late also trips the automatic SOS
    assert [p["hours_ahead"] for p in out["drift"]["points"]] == [0, 1, 3, 6]

    buddy = client.get("/buddies", headers=selvan).json()[0]
    assert buddy["status"] in ("overdue", "emergency") and buddy["lat"] is not None
    alerts = client.get("/alerts/recent?limit=200", headers=ADMIN).json()
    assert any(a["kind"] == "buddy_alert" and "Biju" in a["message"] for a in alerts)


def test_sos_reaches_the_buddy(client):  # noqa: F811
    _, biju = register(client)
    _, selvan = _second(client)
    client.post("/buddies", json={"phone": "+919999900001"}, headers=selvan)
    client.post("/trips/sos", json={**MUTHALAPOZHI, "fix": "gps"}, headers=biju)
    alerts = client.get("/alerts/recent?limit=200", headers=ADMIN).json()
    assert any(a["kind"] == "buddy_alert" and "SOS" in a["message"] for a in alerts)


def test_sms_answers_with_the_engine_verdict(client):  # noqa: F811
    register(client)
    known = client.post("/sms/ask", json={"sender": "+919999900001", "body": "safe tomorrow?"}).json()["reply"]
    assert "Muthalapozhi" in known and "Tomorrow" in known and "SAFE" in known

    forecast.set_scenario("storm")
    stranger = client.post("/sms/ask", json={"sender": "", "body": "KOCHI SMALL"}).json()["reply"]
    assert "Kochi" in stranger and "UNSAFE" in stranger and "1554" in stranger

    helped = client.post("/sms/ask", json={"sender": "", "body": "hello"}).json()["reply"]
    assert "KOCHI MOTOR TOMORROW" in helped


def test_twilio_webhook_replies_in_twiml(client):  # noqa: F811
    resp = client.post("/sms/inbound", content="From=%2B911234567890&Body=VIZHINJAM+BIG",
                       headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert resp.status_code == 200 and "<Message>" in resp.text and "Vizhinjam" in resp.text


# ---- wind and current on the run home ---------------------------------------------------

def test_head_wind_is_the_part_of_the_wind_from_dead_ahead():
    assert drift.head_wind(20, 90, 90) == 20.0       # steering east into an east wind
    assert drift.head_wind(20, 270, 90) == -20.0     # wind from behind
    assert abs(drift.head_wind(20, 0, 90)) < 0.1     # on the beam
    assert drift.head_wind(None, 90, 90) is None


def test_current_against_the_boat_and_compass_names():
    assert drift.against_current(2, 270, 90) == 2.0   # water flowing west, boat steering east
    assert drift.against_current(2, 90, 90) == -2.0
    assert [drift.compass(d) for d in (0, 44, 90, 200, 359)] == ["N", "NE", "E", "S", "N"]
    assert abs(drift.bearing(8.6, 76.7, 8.6, 76.8) - 90) < 1


def test_forecast_carries_wind_current_tide_and_depth_fields(client):  # noqa: F811
    _, headers = register(client)
    sea = client.get("/advisor/forecast", headers=headers).json()["sea"]
    assert sea["wind_from"] == "W" and sea["current_to"] == "NW" and sea["tide_state"] in ("rising", "falling", "slack")
    assert "depth_m" in sea and "head_wind_home" in sea
