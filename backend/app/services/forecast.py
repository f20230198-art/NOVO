"""Open-Meteo marine + weather fetch, sea-point search, 30-minute cache, demo scenarios."""
from __future__ import annotations

import asyncio
import copy
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

log = logging.getLogger("seasafe.forecast")

MARINE_URL = (
    "https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}"
    "&hourly=wave_height,wave_period,wind_wave_height,swell_wave_height&timezone=auto&forecast_days=7"
)
WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
    "&hourly=wind_speed_10m,wind_gusts_10m,precipitation,weather_code,is_day"
    "&wind_speed_unit=kmh&timezone=auto&forecast_days=7"
)
CACHE_TTL_S = 30 * 60
SCENARIOS = ("real", "calm", "rough", "storm", "worsening")

_cache: dict[tuple[float, float], dict] = {}  # key -> {"at": epoch, "data": forecast}
_sea_points: dict[tuple[float, float], tuple[float, float]] = {}
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
            }
        )
    return rows, offset


async def _fetch(lat: float, lon: float) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        slat, slon, marine = await find_sea_point(client, lat, lon)
        weather = await _get_json(client, WEATHER_URL.format(lat=lat, lon=lon))
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


def apply_scenario(rows: list[dict], mode: str, now: datetime) -> list[dict]:
    """Replace forecast values for the demo. `real` returns the rows unchanged."""
    if mode == "real":
        return rows
    out = copy.deepcopy(rows)
    calm = {"wave_height": 0.4, "wave_period": 9.0, "wind_wave_height": 0.2, "swell_wave_height": 0.3,
            "wind_speed": 8.0, "wind_gust": 12.0, "precipitation": 0.0, "weather_code": 1}
    rough = {"wave_height": 1.8, "wave_period": 7.0, "wind_wave_height": 1.3, "swell_wave_height": 1.2,
             "wind_speed": 26.0, "wind_gust": 36.0, "precipitation": 0.5, "weather_code": 3}
    storm = {"wave_height": 3.0, "wave_period": 6.5, "wind_wave_height": 2.4, "swell_wave_height": 1.8,
             "wind_speed": 45.0, "wind_gust": 60.0, "precipitation": 9.0, "weather_code": 95}
    for row in out:
        if mode == "calm":
            row.update(calm)
        elif mode == "rough":
            row.update(rough)
        elif mode == "storm":
            row.update(storm)
        elif mode == "worsening":
            row.update(calm)
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
    out["scenario"] = _scenario
    out["rows"] = apply_scenario(data["rows"], _scenario, _scenario_set_at.astimezone(tz))
    return out
