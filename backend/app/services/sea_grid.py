"""Wave and wind over a small grid of sea points, for the map overlay only.

This never feeds the verdict: the verdict comes from `risk_engine.py` via the advisor at the
fisher's own sea point. The grid only draws the sea state around it (wave texture, wind arrows).
Open-Meteo accepts comma-separated coordinates and answers with one object per point; points on
land come back with null waves and are dropped, so the grid is also the sea mask.
"""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from . import forecast

log = logging.getLogger("seasafe.sea_grid")

MARINE_URL = (
    "https://marine-api.open-meteo.com/v1/marine?latitude={lats}&longitude={lons}"
    "&hourly=wave_height,wave_direction&timezone=GMT&forecast_days=2"
)
WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude={lats}&longitude={lons}"
    "&hourly=wind_speed_10m,wind_direction_10m&wind_speed_unit=kmh&timezone=GMT&forecast_days=2"
)
CACHE_TTL_S = 30 * 60
HOURS = 24
SIZE = 9  # 9 x 9 points: wide enough to fill a phone screen at zoom 10
STEP = 0.1  # degrees, about 11 km

# Direction the wind and swell come FROM when a demo scenario has no real direction to keep:
# the south-west monsoon, the usual rough-weather direction on the Kerala/Karnataka coast.
DEFAULT_WIND_FROM = 240.0
DEFAULT_WAVE_FROM = 250.0

# Charted depth, GEBCO 2020 (about 450 m cells), the same source as advisor.sea_out.
DEPTH_URL = "https://api.opentopodata.org/v1/gebco2020?locations={locations}"
DEPTH_RETRY_S = 10 * 60

_cache: dict[tuple[float, float], dict] = {}
_depth_cache: dict[tuple[float, float], dict[tuple[float, float], Optional[float]]] = {}
_depth_failed_at: dict[tuple[float, float], float] = {}


def clear_cache() -> None:
    _cache.clear()
    _depth_cache.clear()
    _depth_failed_at.clear()


def grid_points(lat: float, lon: float, size: int = SIZE, step: float = STEP) -> list[tuple[float, float]]:
    half = (size - 1) / 2
    return [
        (round(lat + (r - half) * step, 4), round(lon + (c - half) * step, 4))
        for r in range(size)
        for c in range(size)
    ]


def _as_list(data) -> list[dict]:
    # One coordinate returns an object, several return a list.
    return data if isinstance(data, list) else [data]


async def _fetch_grid(lat: float, lon: float) -> dict:
    pts = grid_points(lat, lon)
    lats = ",".join(str(p[0]) for p in pts)
    lons = ",".join(str(p[1]) for p in pts)
    async with httpx.AsyncClient(timeout=12) as client:
        m = await client.get(MARINE_URL.format(lats=lats, lons=lons))
        m.raise_for_status()
        w = await client.get(WEATHER_URL.format(lats=lats, lons=lons))
        w.raise_for_status()
    marine, weather = _as_list(m.json()), _as_list(w.json())
    if len(marine) != len(pts) or len(weather) != len(pts):
        raise ValueError("grid answer does not match the points asked for")

    # Times are fetched in UTC: with timezone=auto, points at sea off Kerala get the Maldives
    # zone (+05:00) while the harbour is +05:30. The offset returned is the harbour's, for display.
    offset = forecast._guess_offset(lat, lon)
    times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in (marine[0].get("hourly") or {}).get("time") or []]

    points = []
    for (plat, plon), mk, wx in zip(pts, marine, weather):
        mh, wh = mk.get("hourly") or {}, wx.get("hourly") or {}
        waves = mh.get("wave_height") or []
        # The marine API snaps a land point to the nearest sea cell, so waves alone do not mark
        # the sea. The weather model's cell elevation does: 0 at sea, above 0 on land.
        if not any(v is not None for v in waves) or (wx.get("elevation") or 0) > 0:
            continue  # land
        w_index = {t: i for i, t in enumerate(wh.get("time") or [])}

        def wind(name: str, t: str):
            j = w_index.get(t)
            values = wh.get(name) or []
            return values[j] if j is not None and j < len(values) else None

        mt = mh.get("time") or []
        points.append(
            {
                "lat": plat,
                "lon": plon,
                "wave": list(waves),
                "wave_dir": list(mh.get("wave_direction") or [None] * len(waves)),
                "wind": [wind("wind_speed_10m", t) for t in mt],
                "wind_dir": [wind("wind_direction_10m", t) for t in mt],
            }
        )
    if not points:
        raise ValueError("no sea points in the grid")
    return {"utc_offset_seconds": offset, "times": times, "points": points, "fetched_at": datetime.now(timezone.utc),
            "synthetic": False}


def _synthetic_grid(lat: float, lon: float) -> dict:
    """Placeholder grid for a demo scenario with no network. Without the marine API we do not know
    where the sea is, so this assumes a west-facing coast (Kerala/Karnataka) and keeps the points
    west of the harbour. It is labelled `synthetic` so the app can say so."""
    offset = forecast._guess_offset(lat, lon)
    tz = timezone(timedelta(seconds=offset))
    start = datetime.now(tz).replace(minute=0, second=0, microsecond=0)
    times = [start + timedelta(hours=h) for h in range(HOURS)]
    points = [
        {"lat": plat, "lon": plon, "wave": [0.5] * HOURS, "wave_dir": [None] * HOURS,
         "wind": [9.0] * HOURS, "wind_dir": [None] * HOURS}
        for plat, plon in grid_points(lat, lon)
        if plon < lon
    ]
    return {"utc_offset_seconds": offset, "times": times, "points": points, "fetched_at": datetime.now(timezone.utc),
            "synthetic": True}


def _offshore_factor(point: dict, lat: float, lon: float) -> float:
    """0.8 at the harbour rising to about 1.25 at the grid edge: seas build away from the coast.
    Used only to give a demo scenario's uniform values a believable spread on the map."""
    d = math.hypot(point["lat"] - lat, point["lon"] - lon)
    edge = STEP * (SIZE - 1) / 2 * math.sqrt(2)
    return 0.8 + 0.45 * min(1.0, d / edge)


def _apply_scenario(grid: dict, mode: str, lat: float, lon: float) -> dict:
    if mode == "real":
        return grid
    # Spatial demo weather (Kerala/Karnataka demo-data session). Optional: the module and the
    # scenario-start getter may not be there, in which case the uniform scenario rows below apply.
    try:
        from . import demo_weather
    except ImportError:
        demo_weather = None
    if demo_weather is not None and mode == getattr(demo_weather, "MODE", None):
        anchor = getattr(forecast, "get_scenario_set_at", lambda: forecast._scenario_set_at)()
        return demo_weather.apply_to_grid(grid, anchor)
    if mode in forecast.SCENARIO_ROWS:
        row = forecast.SCENARIO_ROWS[mode]
    else:  # "worsening" and anything new: the rough row is a fair picture of where it is heading
        row = forecast.SCENARIO_ROWS["rough"]
    points = []
    for p in grid["points"]:
        k = _offshore_factor(p, lat, lon)
        n = len(p["wave"])
        points.append(
            {
                **p,
                "wave": [round(row["wave_height"] * k, 2)] * n,
                "wind": [round(row["wind_speed"] * k, 1)] * n,
                "wave_dir": [d if d is not None else DEFAULT_WAVE_FROM for d in p["wave_dir"]],
                "wind_dir": [d if d is not None else DEFAULT_WIND_FROM for d in p["wind_dir"]],
            }
        )
    return {**grid, "points": points}


def _window(grid: dict, now: datetime) -> dict:
    """The next HOURS hours, starting with the hour in progress."""
    times = grid["times"]
    current = now.replace(minute=0, second=0, microsecond=0)
    start = next((i for i, t in enumerate(times) if t >= current), max(0, len(times) - HOURS))
    end = start + HOURS
    return {
        **grid,
        "times": times[start:end],
        "points": [
            {k: (v[start:end] if isinstance(v, list) else v) for k, v in p.items()} for p in grid["points"]
        ],
    }


async def get_grid(lat: float, lon: float, now: Optional[datetime] = None) -> dict:
    key = (round(lat, 2), round(lon, 2))
    entry = _cache.get(key)
    stale = False
    if entry and time.time() - entry["at"] < CACHE_TTL_S:
        grid = entry["data"]
    else:
        try:
            grid = await _fetch_grid(lat, lon)
            _cache[key] = {"at": time.time(), "data": grid}
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            log.warning("sea grid fetch failed for %s: %s", key, exc)
            if entry:
                grid, stale = entry["data"], True
            elif forecast.get_scenario() != "real":
                grid = _synthetic_grid(lat, lon)
            else:
                raise forecast.ForecastUnavailable(str(exc)) from exc

    mode = forecast.get_scenario()
    out = _window(_apply_scenario(grid, mode, lat, lon), now or datetime.now(timezone.utc))
    # Charted depth is the same in every scenario: it is the sea bed, not the weather.
    depths = await _depths_for(key, [(p["lat"], p["lon"]) for p in out["points"]])
    points = [{**p, "depth": depths.get((p["lat"], p["lon"]))} for p in out["points"]]
    return {
        "center": {"lat": lat, "lon": lon},
        "scenario": mode,
        "synthetic": grid["synthetic"],
        "stale": stale,
        "fetched_at": grid["fetched_at"].isoformat(),
        "utc_offset_seconds": grid["utc_offset_seconds"],
        "times": [t.isoformat() for t in out["times"]],
        "points": points,
    }


async def _depths_for(key: tuple[float, float], pts: list[tuple[float, float]]) -> dict[tuple[float, float], Optional[float]]:
    """Charted depth (m, positive down) for each grid point, or None when unknown.

    The sea bed does not change, so a successful answer is kept for the life of the server.
    The free opentopodata service allows about one call a second and 1000 a day, so after a
    failure it is not asked again for DEPTH_RETRY_S. Without network every depth is None and
    the rest of the grid is unaffected."""
    entry = _depth_cache.get(key)
    if entry is not None and all(p in entry for p in pts):
        return entry
    if time.time() - _depth_failed_at.get(key, 0) < DEPTH_RETRY_S or not pts:
        return entry or {}
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            depths = await _fetch_depths(client, pts)
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        log.warning("depth fetch failed for %s: %s", key, exc)
        _depth_failed_at[key] = time.time()
        return entry or {}
    _depth_cache[key] = {**(entry or {}), **depths}
    return _depth_cache[key]


async def _fetch_depths(client: httpx.AsyncClient, pts: list[tuple[float, float]]) -> dict[tuple[float, float], Optional[float]]:
    out: dict[tuple[float, float], Optional[float]] = {}
    for i in range(0, len(pts), 100):  # 100 locations per call at most
        chunk = pts[i : i + 100]
        resp = await client.get(DEPTH_URL.format(locations="|".join(f"{a},{b}" for a, b in chunk)))
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if len(results) != len(chunk):
            raise ValueError("depth answer does not match the points asked for")
        for p, r in zip(chunk, results):
            elevation = r.get("elevation")
            out[p] = round(-float(elevation), 1) if elevation is not None and float(elevation) < 0 else None
    return out
