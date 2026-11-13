"""Open-Meteo marine + weather fetch, sea-point search, 30-minute cache, demo scenarios."""
from __future__ import annotations

import asyncio
import copy
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from . import demo_weather

log =logging.getLogger("seasafe.forecast")

MARINE_URL = (
    "https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}"
    "&hourly=wave_height,wave_period,wind_wave_height,swell_wave_height,ocean_current_velocity,ocean_current_direction,sea_level_height_msl&timezone=auto&forecast_days=7"
)
WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
    "&hourly=wind_speed_10m,wind_direction_10m,wind_gusts_10m,precipitation,weather_code,is_day"
    "&wind_speed_unit=kmh&timezone=auto&forecast_days=7"
)
# Water depth (GEBCO 2020 grid, about 450 m cells). Optional: the forecast works without it.
DEPTH_URL = "https://api.opentopodata.org/v1/gebco2020?locations={lat},{lon}"
CACHE_TTL_S = 30 * 60
SCENARIOS = ("real", "calm", "rough", "storm", "worsening", "thunderstorm", "heavy_rain", "strong_wind", "high_swell", "cyclone",
             # A whole emulated week that varies by place and hour (services/demo_weather.py).
             "kerala_week")

# Sea and weather values for each simulated condition (applied to every hour).
SCENARIO_ROWS = {
    "calm": {"wave_height": 0.4, "wave_period": 9.0, "wind_wave_height": 0.2, "swell_wave_height": 0.3,
             "wind_speed": 8.0, "wind_gust": 12.0, "precipitation": 0.0, "weather_code": 1},
    "rough": {"wave_height": 1.8, "wave_period": 7.0, "wind_wave_height": 1.3, "swell_wave_height": 1.2,
              "wind_speed": 26.0, "wind_gust": 36.0, "precipitation": 0.5, "weather_code": 3},
    "storm": {"wave_height": 3.0, "wave_period": 6.5, "wind_wave_height": 2.4, "swell_wave_height": 1.8,
              "wind_speed": 45.0, "wind_gust": 60.0, "precipitation": 9.0, "weather_code": 95},
    # Lightning: UNSAFE for every boat even though the sea itself is moderate.
    "thunderstorm": {"wave_height": 1.1, "wave_period": 7.5, "wind_wave_height": 0.8, "swell_wave_height": 0.7,
                     "wind_speed": 24.0, "wind_gust": 45.0, "precipitation": 6.0, "weather_code": 95},
    # Heavy rain, poor visibility: CAUTION for most boats.
    "heavy_rain": {"wave_height": 0.9, "wave_period": 8.0, "wind_wave_height": 0.5, "swell_wave_height": 0.6,
                   "wind_speed": 18.0, "wind_gust": 28.0, "precipitation": 12.0, "weather_code": 65},
    # Gale-force wind with a building sea.
    "strong_wind": {"wave_height": 2.0, "wave_period": 6.0, "wind_wave_height": 1.7, "swell_wave_height": 0.9,
                    "wind_speed": 48.0, "wind_gust": 66.0, "precipitation": 0.0, "weather_code": 3},
    # Long-period swell from a distant storm: calm wind, big waves.
    "high_swell": {"wave_height": 2.7, "wave_period": 13.0, "wind_wave_height": 0.3, "swell_wave_height": 2.6,
                   "wind_speed": 10.0, "wind_gust": 16.0, "precipitation": 0.0, "weather_code": 2},
    # Cyclone: the worst of everything (the simulation also posts an official warning).
    "cyclone": {"wave_height": 4.5, "wave_period": 8.0, "wind_wave_height": 3.2, "swell_wave_height": 3.4,
                "wind_speed": 75.0, "wind_gust": 100.0, "precipitation": 25.0, "weather_code": 99},
}

_cache: dict[tuple[float, float], dict] = {}  # key -> {"at": epoch, "data": forecast}
_sea_points: dict[tuple[float, float], tuple[float, float]] = {}
_depths: dict[tuple[float, float], Optional[float]] = {}
_scenario = "real"
_scenario_set_at = datetime.now(timezone.utc)


class ForecastUnavailable(Exception):
    pass


def set_scenario(mode: str) -> None:
    global _scenario, _scenario_set_at
    if mode not in SCENARIOS:
        raise ValueError(f"unknown scenario {mode}")
    _scenario = mode
    _scenario_set_at = datetime.now(timezone.utc)


def get_scenario() -> str:
    return _scenario


def get_scenario_set_at() -> datetime:
    """When the current scenario was switched on (UTC, on the hour). Time-varying scenarios count from here."""
    return _scenario_set_at.replace(minute=0, second=0, microsecond=0)


def clear_cache() -> None:
    _cache.clear()
    _sea_points.clear()


async def _get_json(client: httpx.AsyncClient, url: str) -> dict:
    resp = await client.get(url)
    resp.raise_for_status()
    return resp.json()


def _has_waves(marine: dict) -> bool:
    values = (marine.get("hourly") or {}).get("wave_height") or []
    return any(v is not None for v in values)


async def find_sea_point(client: httpx.AsyncClient, lat: float, lon: float) -> tuple[float, float, dict]:
    """Marine data for the nearest point that is actually at sea.

    Points on land return null waves, so try 8 directions at 0.05, 0.1 and 0.2 degrees.
    """
    key = (round(lat, 2), round(lon, 2))
    if key in _sea_points:
        slat, slon = _sea_points[key]
        return slat, slon, await _get_json(client, MARINE_URL.format(lat=slat, lon=slon))

    marine = await _get_json(client, MARINE_URL.format(lat=lat, lon=lon))
    if _has_waves(marine):
        _sea_points[key] = (lat, lon)
        return lat, lon, marine

    directions = [(0, -1), (-1, -1), (1, -1), (-1, 0), (1, 0), (0, 1), (-1, 1), (1, 1)]  # (dlat, dlon), west first
    for step in (0.05, 0.1, 0.2):
        for dlat, dlon in directions:
            slat, slon = round(lat + dlat * step, 4), round(lon + dlon * step, 4)
            try:
                marine = await _get_json(client, MARINE_URL.format(lat=slat, lon=slon))
            except httpx.HTTPError:
                continue
            if _has_waves(marine):
                _sea_points[key] = (slat, slon)
                return slat, slon, marine
    raise ForecastUnavailable("no sea point with wave data near this location")


async def water_depth(client: httpx.AsyncClient, lat: float, lon: float) -> Optional[float]:
    """Charted depth in metres at a sea point (positive down), or None when it is not known."""
    key = (round(lat, 3), round(lon, 3))
    if key in _depths:
        return _depths[key]
    try:
        resp = await client.get(DEPTH_URL.format(lat=lat, lon=lon), timeout=4)
        resp.raise_for_status()
        elevation = (resp.json().get("results") or [{}])[0].get("elevation")
        depth = round(-float(elevation), 1) if elevation is not None and float(elevation) < 0 else None
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError):
        return None  # not cached: try again next time
    _depths[key] = depth
    return depth


def _merge(marine: dict, weather: dict) -> tuple[list[dict], int]:
    offset = int(marine.get("utc_offset_seconds") or weather.get("utc_offset_seconds") or 0)
    tz = timezone(timedelta(seconds=offset))
    mh, wh = marine.get("hourly") or {}, weather.get("hourly") or {}
    w_index = {t: i for i, t in enumerate(wh.get("time") or [])}

    def pick(src: dict, name: str, i: Optional[int]):
        values = src.get(name) or []
        return values[i] if i is not None and i < len(values) else None

    rows = []
    for i, t in enumerate(mh.get("time") or []):
        j = w_index.get(t)
        rows.append(
            {
                "time": datetime.fromisoformat(t).replace(tzinfo=tz),
                "wave_height": pick(mh, "wave_height", i),
                "wave_period": pick(mh, "wave_period", i),
                "wind_wave_height": pick(mh, "wind_wave_height", i),
                "swell_wave_height": pick(mh, "swell_wave_height", i),
                "wind_speed": pick(wh, "wind_speed_10m", j),
                "wind_gust": pick(wh, "wind_gusts_10m", j),
                "precipitation": pick(wh, "precipitation", j),
                "weather_code": pick(wh, "weather_code", j),
                "is_day": pick(wh, "is_day", j),
                # For the drift search zone and the harbour-mouth estimate. Current direction is
                # where the water flows TO; wind direction is where the wind comes FROM.
                "current_speed": pick(mh, "ocean_current_velocity", i),
                "current_dir": pick(mh, "ocean_current_direction", i),
                "sea_level": pick(mh, "sea_level_height_msl", i),
                "wind_dir": pick(wh, "wind_direction_10m", j),
            }
        )
    return rows, offset


async def _fetch(lat: float, lon: float) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        slat, slon, marine = await find_sea_point(client, lat, lon)
        # Wind at the sea point, not at the harbour: wind over land reads lower than at sea,
        # which would make the verdict too optimistic.
        weather = await _get_json(client, WEATHER_URL.format(lat=slat, lon=slon))
        depth = await water_depth(client, slat, slon)
    rows, offset = _merge(marine, weather)
    if not rows:
        raise ForecastUnavailable("empty forecast")
    return {
        "lat": lat,
        "lon": lon,
        "sea_lat": slat,
        "sea_lon": slon,
        "utc_offset_seconds": offset,
        "rows": rows,
        "depth_m": depth,
        "fetched_at": datetime.now(timezone.utc),
        "stale": False,
        "synthetic": False,
    }


def _guess_offset(lat: float, lon: float) -> int:
    if 6 <= lat <= 36 and 68 <= lon <= 97:
        return 19800  # India
    return int(round(lon / 15)) * 3600


def _synthetic(lat: float, lon: float) -> dict:
    """Calm placeholder rows, used only when a demo scenario is on and the network is down."""
    offset = _guess_offset(lat, lon)
    tz = timezone(timedelta(seconds=offset))
    start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = [
        {
            "time": start + timedelta(hours=h),
            "wave_height": 0.5,
            "wave_period": 9.0,
            "wind_wave_height": 0.2,
            "swell_wave_height": 0.4,
            "wind_speed": 9.0,
            "wind_gust": 14.0,
            "precipitation": 0.0,
            "weather_code": 1,
            "is_day": 1 if 6 <= (h % 24) < 18 else 0,
            "current_speed": 1.2,
            "current_dir": 330.0,
            "sea_level": round(0.35 * math.sin(2 * math.pi * h / 12.42), 3),
            "wind_dir": 290.0,
        }
        for h in range(7 * 24)
    ]
    return {
        "lat": lat,
        "lon": lon,
        "sea_lat": lat,
        "sea_lon": lon,
        "utc_offset_seconds": offset,
        "rows": rows,
        "fetched_at": datetime.now(timezone.utc),
        "stale": False,
        "synthetic": True,
    }


def apply_scenario(rows: list[dict], mode: str, now: datetime,
                   lat: Optional[float] = None, lon: Optional[float] = None) -> list[dict]:
    """Replace forecast values for the demo. `real` returns the rows unchanged.

    `lat`/`lon` (the sea point) only matter for scenarios that vary by place.
    """
    if mode == "real":
        return rows
    out = copy.deepcopy(rows)
    if mode == demo_weather.MODE:
        # Floored in UTC, the same as get_scenario_set_at(), so the map grid and this point agree.
        anchor = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        return demo_weather.apply_to_rows(out, 8.377 if lat is None else lat, 76.96 if lon is None else lon, anchor)
    for row in out:
        if mode in SCENARIO_ROWS:
            row.update(SCENARIO_ROWS[mode])
            if row.get("current_speed") is None:
                row.update({"current_speed": 1.2, "current_dir": 330.0})
            if row.get("wind_dir") is None:
                row["wind_dir"] = 290.0
        elif mode == "worsening":
            row.update(SCENARIO_ROWS["calm"])
            # `now` is when the scenario was switched on. Calm for the two hour slots
            # in progress, then the sea gets up quickly and stays up.
            anchor = now.replace(minute=0, second=0, microsecond=0)
            lead_h = (row["time"] - anchor).total_seconds() / 3600
            if lead_h >= 2:
                first = lead_h < 3
                row.update(
                    {
                        "wave_height": 2.6 if first else 2.8,
                        "wave_period": 6.5,
                        "wind_wave_height": 2.0,
                        "wind_speed": 36.0 if first else 42.0,
                        "wind_gust": 58.0,
                        "precipitation": 3.0,
                        "weather_code": 63,
                    }
                )
    return out


async def get_forecast(lat: float, lon: float) -> dict:
    """Forecast for a point: fresh, cached (<30 min), or stale cache on network failure.

    The active demo scenario is applied on top. Raises ForecastUnavailable when there is
    no data at all and no demo scenario to fall back on.
    """
    key = (round(lat, 2), round(lon, 2))
    entry = _cache.get(key)
    data: Optional[dict] = None
    if entry and time.time() - entry["at"] < CACHE_TTL_S:
        data = entry["data"]
    else:
        try:
            data = await _fetch(lat, lon)
            _cache[key] = {"at": time.time(), "data": data}
        except (httpx.HTTPError, ForecastUnavailable, asyncio.TimeoutError, ValueError, KeyError) as exc:
            log.warning("forecast fetch failed for %s: %s", key, exc)
            if entry:
                data = {**entry["data"], "stale": True}
            elif _scenario != "real":
                data = _synthetic(lat, lon)
            else:
                raise ForecastUnavailable(str(exc)) from exc

    tz = timezone(timedelta(seconds=data["utc_offset_seconds"]))
    out = dict(data)
    # How old the data is. The advisor stops calling anything SAFE once this passes
    # `stale_forecast_minutes` in thresholds.json.
    out["age_minutes"] = max(0, int((datetime.now(timezone.utc) - data["fetched_at"]).total_seconds() // 60))
    out["scenario"] = _scenario
    out["rows"] = apply_scenario(data["rows"], _scenario, _scenario_set_at.astimezone(tz), data["sea_lat"], data["sea_lon"])
    return out
