"""Emulated week of weather off south Kerala, for the `kerala_week` demo scenario.

Pure and deterministic: the same point, time and anchor always give the same values. It only
replaces forecast numbers; the verdict still comes from `risk_engine.py`, exactly as for real data.

Story of the week (hours are counted from `anchor`, when the scenario was switched on):
  0-26 h   fair weather. Land breeze from the east at night, sea breeze from the west in the
           afternoon (enough to make a catamaran CAUTION, not a motorised boat), 0.7 m swell.
  26-36 h  a low over the Comorin area deepens; wind backs WSW and freshens, rain arrives.
  36-54 h  rough spell: 40-50 km/h WSW, gusts 60+, 2.5-3.5 m sea, thunderstorms in the
           afternoon and evening. Worst in the south (towards Kanyakumari) and offshore.
  54-72 h  easing, wind veers west.
  72-110 h leftover swell, 1.3 m decaying to 0.8 m: CAUTION for the small boats.
  110 h-   fair again.
The leftover swell is long-period, so the harbour-mouth estimate (`risk_engine.bar_*`) is worse
than the open sea on a falling tide: a good demo of "fine outside, dangerous at the bar".
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

MODE = "kerala_week"
IST = timezone(timedelta(hours=5, minutes=30))

# South Kerala coastline, south to north: (lat, lon). Sea is to the west of it.
COAST = [
    (8.08, 77.55),   # Kanyakumari
    (8.13, 77.40),
    (8.17, 77.26),   # Colachel
    (8.26, 77.15),
    (8.31, 77.07),   # Poovar
    (8.377, 76.99),  # Vizhinjam
    (8.40, 76.97),   # Kovalam
    (8.47, 76.91),   # Shanghumugham
    (8.55, 76.85),   # Veli / Thumba
    (8.64, 76.775),  # Muthalapozhi
    (8.73, 76.71),   # Varkala
    (8.88, 76.58),   # Kollam
    (9.10, 76.47),
    (9.49, 76.32),   # Alappuzha
    (9.97, 76.24),   # Kochi
]

# Spell timing, hours after the anchor.
BUILD_START, PEAK_START, PEAK_END, EASE_END, SWELL_END = 26.0, 36.0, 54.0, 72.0, 110.0


def coast_lon(lat: float) -> float:
    """Longitude of the coastline at this latitude (south of Kanyakumari it is all sea)."""
    if lat < COAST[0][0]:
        return 78.5
    for (la1, lo1), (la2, lo2) in zip(COAST, COAST[1:]):
        if la1 <= lat <= la2:
            f = (lat - la1) / (la2 - la1)
            return lo1 + f * (lo2 - lo1)
    return COAST[-1][1]


def is_sea(lat: float, lon: float) -> bool:
    return lon < coast_lon(lat) - 0.01


def offshore_km(lat: float, lon: float) -> float:
    # The coast runs NNW-SSE, so the perpendicular distance is a bit under the east-west one.
    return max(0.0, (coast_lon(lat) - lon) * 111.0 * math.cos(math.radians(lat)) * 0.85)


def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def spell(lead_h: float) -> float:
    """0 = fair weather, 1 = the height of the rough spell."""
    if lead_h < BUILD_START or lead_h >= EASE_END:
        return 0.0
    if lead_h < PEAK_START:
        return _smooth((lead_h - BUILD_START) / (PEAK_START - BUILD_START))
    if lead_h < PEAK_END:
        return 1.0
    return 1.0 - _smooth((lead_h - PEAK_END) / (EASE_END - PEAK_END))


def leftover_swell(lead_h: float) -> float:
    """Extra swell (m) left behind after the spell."""
    if lead_h < PEAK_END or lead_h >= SWELL_END:
        return 0.0
    if lead_h < EASE_END:
        return 0.6 * _smooth((lead_h - PEAK_END) / (EASE_END - PEAK_END))
    return 0.6 * (1.0 - (lead_h - EASE_END) / (SWELL_END - EASE_END))


def _breeze(hour: float) -> tuple[float, float]:
    """Fair-weather wind (km/h, direction FROM in degrees) for a local hour."""
    sea = math.sin(math.pi * (hour - 10) / 9) if 10 <= hour <= 19 else 0.0
    if sea > 0:
        return 9.0 + 13.0 * sea, 265.0  # afternoon sea breeze from the west
    return 8.0 + 2.0 * math.cos(math.pi * hour / 12), 65.0  # night/morning land breeze from ENE


def _blend_dir(a: float, b: float, f: float) -> float:
    d = ((b - a + 180) % 360) - 180
    return (a + d * f) % 360


def values_at(lat: float, lon: float, t: datetime, anchor: datetime) -> dict:
    """Forecast row values for one sea point and hour (same keys as forecast rows, plus directions)."""
    lead = (t - anchor).total_seconds() / 3600
    hour = t.astimezone(IST).hour + t.astimezone(IST).minute / 60
    s = spell(lead)
    south = min(1.0, max(0.0, (8.9 - lat) / 0.8))  # 1 near Kanyakumari, ~0.65 at Vizhinjam
    fetch = 0.55 + 0.45 * min(1.0, max(offshore_km(lat, lon), 3.0) / 25.0)
    ripple = 0.06 * math.sin(lat * 37.0 + lon * 23.0 + lead / 5.0)  # a little texture for the map

    calm_wind, calm_dir = _breeze(hour)
    storm_wind = 40.0 + 9.0 * south + 4.0 * math.sin(lead / 3.0)
    storm_dir = _blend_dir(245.0, 280.0, max(0.0, (lead - PEAK_END) / (EASE_END - PEAK_END)))
    wind = calm_wind + (storm_wind - calm_wind) * s
    wind *= 0.85 + 0.25 * fetch  # stronger offshore, sheltered close in
    wind_dir = _blend_dir(calm_dir, storm_dir, s)
    gust = wind * (1.35 + 0.1 * s)

    swell = (0.7 + 0.08 * math.sin(lead / 30.0) + leftover_swell(lead) + 1.6 * s * (0.7 + 0.3 * south))
    swell *= 0.8 + 0.2 * fetch
    wind_wave = (0.12 + 0.9 * (wind / 40.0) ** 2) * fetch
    wave = math.sqrt(swell ** 2 + wind_wave ** 2) * (1 + ripple)
    period = 10.0 - 3.5 * s + 1.0 * min(1.0, leftover_swell(lead) / 0.6) * (1 - s)

    # Coastal current runs north-north-west along the shore in this season (flows TO, km/h),
    # stronger and more northerly while the spell blows.
    current = (0.9 + 0.2 * math.sin(lead / 9.0)) * (1 + 1.1 * s) * (0.7 + 0.3 * fetch)
    current_dir = _blend_dir(330.0, 350.0, s)
    # Mixed semi-diurnal tide (about 0.3 m range each way on this coast), from absolute time so
    # it is continuous across reloads, plus a small surge in the spell.
    th = t.timestamp() / 3600
    tide = 0.28 * math.sin(2 * math.pi * th / 12.42) + 0.07 * math.sin(2 * math.pi * th / 12.0 + 1.0) + 0.15 * s

    if s > 0.8 and 14 <= hour < 23:
        code, rain = 95, 9.0 + 4.0 * south
    elif s > 0.5:
        code, rain = 63, 4.0 + 3.0 * s
    elif s > 0.15:
        code, rain = 80, 1.5 * s * 4
    else:
        code, rain = (2 if 12 <= hour < 18 else 1), 0.0

    return {
        "wave_height": round(wave, 2),
        "wave_period": round(period, 1),
        "wind_wave_height": round(wind_wave, 2),
        "swell_wave_height": round(swell, 2),
        "wind_speed": round(wind, 1),
        "wind_gust": round(gust, 1),
        "precipitation": round(rain, 1),
        "weather_code": code,
        "wind_dir": round(wind_dir),  # FROM, degrees (same key as real forecast rows)
        "wave_direction": round(_blend_dir(225.0, 245.0, s)),  # FROM, degrees
        "current_speed": round(current, 2),  # km/h, like Open-Meteo
        "current_dir": round(current_dir),  # TO, degrees
        "sea_level": round(tide, 3),  # m above mean sea level
        "is_day": 1 if 6 <= hour < 18.5 else 0,
    }


def apply_to_rows(rows: list[dict], lat: float, lon: float, anchor: datetime) -> list[dict]:
    """Replace the values of forecast rows (already deep-copied by the caller) for one point."""
    if not is_sea(lat, lon):  # the advisor's point should be at sea; nudge a harbour point offshore
        lon = coast_lon(lat) - 0.03
    for row in rows:
        row.update(values_at(lat, lon, row["time"], anchor))
    return rows


def apply_to_grid(grid: dict, anchor: datetime) -> dict:
    """Fill a `sea_grid` grid ({times, points: [{lat, lon, wave, wave_dir, wind, wind_dir}]}).

    Land points (by the coastline above) are dropped, so the map never draws waves on land.
    """
    points = []
    for p in grid["points"]:
        if not is_sea(p["lat"], p["lon"]):
            continue
        vals = [values_at(p["lat"], p["lon"], t, anchor) for t in grid["times"]]
        points.append({
            **p,
            "wave": [v["wave_height"] for v in vals],
            "wave_dir": [v["wave_direction"] for v in vals],
            "wind": [v["wind_speed"] for v in vals],
            "wind_dir": [v["wind_dir"] for v in vals],
        })
    return {**grid, "points": points}


def grid_points(lat_min: float = 7.9, lat_max: float = 9.0, lon_min: float = 76.2, lon_max: float = 77.6,
                step: float = 0.1, max_offshore_km: float = 60.0) -> list[tuple[float, float]]:
    """Sea points of a regular grid off south Kerala (used by tests and the demo grid route)."""
    out = []
    n_lat = int(round((lat_max - lat_min) / step)) + 1
    n_lon = int(round((lon_max - lon_min) / step)) + 1
    for i in range(n_lat):
        for j in range(n_lon):
            la, lo = round(lat_min + i * step, 3), round(lon_min + j * step, 3)
            if is_sea(la, lo) and offshore_km(la, lo) <= max_offshore_km:
                out.append((la, lo))
    return out
