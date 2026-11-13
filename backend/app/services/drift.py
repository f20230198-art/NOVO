"""Drift search zone: where a boat without power has probably been carried.

Pure functions: no I/O, no clock, no database. Given the last known position, the time of
that position and the hourly forecast rows, it integrates

    drift velocity = ocean current + leeway_factor x wind

hour by hour and returns a centre and a search radius for "now" and a few hours ahead.
The radius grows with time and with the distance drifted, because both the forecast and
the leeway of a small boat are uncertain. It is a place to start searching, not a fix.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional

KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON = 111.320


def _row_at(rows: list[dict], t: datetime) -> Optional[dict]:
    """The forecast hour containing t, else the nearest one within 3 hours."""
    best, best_gap = None, None
    for r in rows:
        if r["time"] <= t < r["time"] + timedelta(hours=1):
            return r
        gap = abs((r["time"] - t).total_seconds())
        if best_gap is None or gap < best_gap:
            best, best_gap = r, gap
    return best if best_gap is not None and best_gap <= 3 * 3600 else None


def velocity(row: Optional[dict], leeway_factor: float) -> tuple[float, float, bool, bool]:
    """(east km/h, north km/h, used current, used wind) for one forecast hour."""
    east = north = 0.0
    used_current = used_wind = False
    if row is None:
        return east, north, used_current, used_wind
    speed, direction = row.get("current_speed"), row.get("current_dir")
    if speed is not None and direction is not None:
        rad = math.radians(float(direction))  # flows TO this bearing
        east += float(speed) * math.sin(rad)
        north += float(speed) * math.cos(rad)
        used_current = True
    wind, wind_from = row.get("wind_speed"), row.get("wind_dir")
    if wind is not None and wind_from is not None:
        rad = math.radians((float(wind_from) + 180.0) % 360.0)  # blows TO this bearing
        east += leeway_factor * float(wind) * math.sin(rad)
        north += leeway_factor * float(wind) * math.cos(rad)
        used_wind = True
    return east, north, used_current, used_wind


def _move(lat: float, lon: float, east_km: float, north_km: float) -> tuple[float, float]:
    lat2 = lat + north_km / KM_PER_DEG_LAT
    lon2 = lon + east_km / (KM_PER_DEG_LON * max(0.2, math.cos(math.radians(lat))))
    return lat2, lon2


def predict(lat: float, lon: float, since: datetime, now: datetime, rows: list[dict], cfg: dict) -> dict:
    """Search zone from the last known position (`since`) to `now` and the hours ahead.

    `since` and `now` are timezone-aware. Returns
    {basis, since, hours_adrift, speed_kmh, heading_deg, points: [{hours_ahead, at, lat, lon, radius_km, drifted_km}]}.
    `basis` says what the estimate rests on: "current+wind", "current", "wind" or "none".
    """
    leeway = float(cfg.get("leeway_factor", 0.03))
    base = float(cfg.get("base_radius_km", 0.5))
    per_hour = float(cfg.get("radius_km_per_hour", 0.35))
    per_km = float(cfg.get("radius_per_km_drifted", 0.3))
    max_hours = float(cfg.get("max_hours", 72))
    ahead = sorted({float(h) for h in cfg.get("hours_ahead", [0, 1, 3, 6])})

    if now < since:
        since = now
    if (now - since).total_seconds() / 3600 > max_hours:
        since = now - timedelta(hours=max_hours)

    points: list[dict] = []
    t, cur_lat, cur_lon, path_km = since, lat, lon, 0.0
    any_current = any_wind = False
    last_v = (0.0, 0.0)
    for h in ahead:
        target = now + timedelta(hours=h)
        while t < target:
            # Step to the next hour boundary or the target, whichever comes first.
            next_hour = t.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            step_end = min(next_hour, target)
            dt_h = (step_end - t).total_seconds() / 3600
            east, north, used_c, used_w = velocity(_row_at(rows, t), leeway)
            any_current, any_wind = any_current or used_c, any_wind or used_w
            cur_lat, cur_lon = _move(cur_lat, cur_lon, east * dt_h, north * dt_h)
            path_km += math.hypot(east, north) * dt_h
            last_v = (east, north)
            t = step_end
        hours_total = (target - since).total_seconds() / 3600
        points.append({
            "hours_ahead": h,
            "at": target.isoformat(),
            "lat": round(cur_lat, 5),
            "lon": round(cur_lon, 5),
            "radius_km": round(base + per_hour * hours_total + per_km * path_km, 2),
            "drifted_km": round(path_km, 2),
        })

    basis = "current+wind" if any_current and any_wind else "current" if any_current else "wind" if any_wind else "none"
    speed = math.hypot(*last_v)
    heading = (math.degrees(math.atan2(last_v[0], last_v[1])) + 360) % 360 if speed > 0 else None
    return {
        "basis": basis,
        "since": since.isoformat(),
        "hours_adrift": round((now - since).total_seconds() / 3600, 2),
        "speed_kmh": round(speed, 2),
        "heading_deg": round(heading) if heading is not None else None,
        "points": points,
    }


COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def compass(degrees: Optional[float]) -> Optional[str]:
    """Eight-point compass name for a bearing."""
    if degrees is None:
        return None
    return COMPASS[int((float(degrees) % 360 + 22.5) // 45) % 8]


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing in degrees from point 1 to point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def head_wind(wind_speed: Optional[float], wind_from: Optional[float], course: Optional[float]) -> Optional[float]:
    """Wind component against a boat steering `course`: positive is a head wind, negative a
    tail wind. Wind direction is where it blows FROM, so a wind from dead ahead is all head wind."""
    if wind_speed is None or wind_from is None or course is None:
        return None
    return round(float(wind_speed) * math.cos(math.radians(float(wind_from) - float(course))), 1)


def against_current(speed: Optional[float], flows_to: Optional[float], course: Optional[float]) -> Optional[float]:
    """Current component against a boat steering `course` (positive slows the boat down)."""
    if speed is None or flows_to is None or course is None:
        return None
    return round(-float(speed) * math.cos(math.radians(float(flows_to) - float(course))), 1)
