"""Map sea-state grid: land points dropped, demo scenarios applied, no verdict in the payload."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import forecast, sea_grid

HARBOUR = {"lat": 12.87, "lon": 74.83}  # Mangaluru
IST = timezone(timedelta(seconds=19800))


def fake_answer(points, sea_west_of):
    """Open-Meteo style multi-point answers: points east of `sea_west_of` are land."""
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=3)
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(48)]  # timezone=GMT
    marine, weather = [], []
    for lat, lon in points:
        sea = lon < sea_west_of
        # Like the real API: the marine model snaps land to a sea cell, so land still has waves;
        # only the weather model's elevation tells land from sea.
        marine.append({"utc_offset_seconds": 0, "hourly": {
            "time": times,
            "wave_height": [round(1.0 + abs(sea_west_of - lon), 2) for _ in times],
            "wave_direction": [250 for _ in times]}})
        weather.append({"utc_offset_seconds": 0, "elevation": 0.0 if sea else 40.0, "hourly": {
            "time": times, "wind_speed_10m": [20.0 for _ in times], "wind_direction_10m": [230 for _ in times]}})
    return marine, weather


@pytest.fixture()
def client(monkeypatch):
    async def no_depths(client, pts):
        raise httpx.ConnectError("network disabled in tests")

    monkeypatch.setattr(sea_grid, "_fetch_depths", no_depths)
    sea_grid.clear_cache()
    forecast.set_scenario("real")
    yield TestClient(app)
    forecast.set_scenario("real")
    sea_grid.clear_cache()


def patch_network(monkeypatch, sea_west_of=74.83):
    async def fake_fetch(lat, lon):
        pts = sea_grid.grid_points(lat, lon)
        marine, weather = fake_answer(pts, sea_west_of)

        class R:
            def __init__(self, data):
                self.data = data

            def json(self):
                return self.data

            def raise_for_status(self):
                pass

        class Client:
            def __init__(self, *a, **k):
                self.calls = 0

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url):
                self.calls += 1
                return R(marine if "marine" in url else weather)

        monkeypatch.setattr(sea_grid.httpx, "AsyncClient", Client)
        return await original(lat, lon)

    original = sea_grid._fetch_grid
    monkeypatch.setattr(sea_grid, "_fetch_grid", fake_fetch)


def test_grid_keeps_sea_points_and_starts_at_this_hour(client, monkeypatch):
    patch_network(monkeypatch)
    resp = client.get("/forecast/grid", params=HARBOUR)
    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario"] == "real" and body["synthetic"] is False
    assert 0 < len(body["points"]) < sea_grid.SIZE ** 2  # land points dropped
    assert all(p["lon"] < HARBOUR["lon"] for p in body["points"])
    assert len(body["times"]) == sea_grid.HOURS
    first = datetime.fromisoformat(body["times"][0])
    assert first <= datetime.now(IST) < first + timedelta(hours=1)
    assert body["utc_offset_seconds"] == 19800  # the harbour's zone, not the Maldives'
    p = body["points"][0]
    assert len(p["wave"]) == len(p["wind"]) == len(p["wind_dir"]) == sea_grid.HOURS
    # Map data only: nothing in it looks like a verdict.
    assert "verdict" not in resp.text and "SAFE" not in resp.text


def test_demo_scenario_overrides_values_and_grows_offshore(client, monkeypatch):
    patch_network(monkeypatch)
    forecast.set_scenario("storm")
    body = client.get("/forecast/grid", params=HARBOUR).json()
    assert body["scenario"] == "storm"
    waves = sorted(p["wave"][0] for p in body["points"])
    storm = forecast.SCENARIO_ROWS["storm"]["wave_height"]
    assert storm * 0.8 - 0.01 <= waves[0] < waves[-1] <= storm * 1.25 + 0.01


def test_no_network_real_mode_is_503_but_demo_gets_labelled_placeholder(client, monkeypatch):
    async def down(lat, lon):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(sea_grid, "_fetch_grid", down)
    assert client.get("/forecast/grid", params=HARBOUR).status_code == 503

    forecast.set_scenario("rough")
    body = client.get("/forecast/grid", params=HARBOUR).json()
    assert body["synthetic"] is True
    assert body["points"] and all(p["wind_dir"][0] == sea_grid.DEFAULT_WIND_FROM for p in body["points"])


def test_stale_cache_is_used_and_flagged_when_the_network_drops(client, monkeypatch):
    patch_network(monkeypatch)
    assert client.get("/forecast/grid", params=HARBOUR).status_code == 200
    key = (round(HARBOUR["lat"], 2), round(HARBOUR["lon"], 2))
    sea_grid._cache[key]["at"] -= sea_grid.CACHE_TTL_S + 1

    async def down(lat, lon):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(sea_grid, "_fetch_grid", down)
    body = client.get("/forecast/grid", params=HARBOUR).json()
    assert body["stale"] is True and body["points"]


def test_depth_is_attached_cached_and_never_breaks_the_grid(client, monkeypatch):
    patch_network(monkeypatch)
    calls = []

    async def depths(client, pts):
        calls.append(len(pts))
        return {p: round((HARBOUR["lon"] - p[1]) * 400, 1) for p in pts}  # deeper offshore

    monkeypatch.setattr(sea_grid, "_fetch_depths", depths)
    body = client.get("/forecast/grid", params=HARBOUR).json()
    assert all(p["depth"] is not None and p["depth"] > 0 for p in body["points"])
    client.get("/forecast/grid", params=HARBOUR)
    assert len(calls) == 1  # the sea bed is asked for once


def test_depth_offline_is_null_and_not_retried_at_once(client, monkeypatch):
    patch_network(monkeypatch)
    calls = []

    async def down(client, pts):
        calls.append(1)
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(sea_grid, "_fetch_depths", down)
    body = client.get("/forecast/grid", params=HARBOUR).json()
    assert body["points"] and all(p["depth"] is None for p in body["points"])
    client.get("/forecast/grid", params=HARBOUR)
    assert len(calls) == 1  # backs off instead of hammering the free service


def test_grid_is_centred_on_the_point():
    pts = sea_grid.grid_points(10.0, 76.0)
    assert len(pts) == sea_grid.SIZE ** 2
    assert (10.0, 76.0) in pts
