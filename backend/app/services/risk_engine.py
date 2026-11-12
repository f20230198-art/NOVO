"""Sea Safe risk engine.

Pure, deterministic functions only: no I/O, no clock, no database, no network.
This module is the ONLY place a SAFE / CAUTION / UNSAFE verdict is decided.

Inputs
- rows: hourly forecast dicts with an aware local `time` (see services/forecast.py)
- boat: "non_motorised" | "motorised" | "mechanised"
- thresholds: the parsed thresholds.json
- warnings: dicts {title, center_lat, center_lon, radius_km, starts_at, expires_at}
- reports: dicts {type, lat, lon, created_at, expires_at, up, down}
- point: optional (lat, lon). When given, warnings and reports are filtered by
  distance here; when omitted the caller must pass only the relevant ones.

Official warnings and community reports can only raise a level, never lower it.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

SAFE, CAUTION, UNSAFE = "SAFE", "CAUTION", "UNSAFE"
LEVEL_ORDER = {SAFE: 0, CAUTION: 1, UNSAFE: 2}
SEA_STATE_REPORT_TYPES = {"rough_sea", "storm", "harbour_mouth_rough"}
# Tie-break when several reasons share a level: which one to mention first.
FACTOR_PRIORITY = [
    "official_warning", "weather_code", "wave_height", "wind_gust", "wind_speed",
    "wave_period", "precipitation", "community_reports", "night", "data_missing",
]


@dataclass
class Reason:
    factor: str
    value: Optional[float]
    unit: str
    threshold: Optional[float]
    level: str
    text_key: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HourRisk:
    time: datetime
    level: str
    reasons: list[Reason] = field(default_factory=list)
    is_day: bool = True

    def to_dict(self) -> dict:
        return {
            "time": self.time.isoformat(),
            "level": self.level,
            "is_day": self.is_day,
            "reasons": [r.to_dict() for r in self.reasons],
        }


def max_level(*levels: str) -> str:
    return max(levels, key=lambda lv: LEVEL_ORDER[lv]) if levels else SAFE


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _graded(value: Optional[float], caution: float, unsafe: float) -> Optional[tuple[str, float]]:
    """Return (level, threshold crossed) for a 'bigger is worse' factor, or None if fine."""
    if value is None:
        return None
    if value > unsafe:
        return UNSAFE, unsafe
    if value > caution:
        return CAUTION, caution
    return None


def evaluate_hour(
    row: dict,
    boat: str,
    thresholds: dict,
    warnings: Optional[list[dict]] = None,
    reports: Optional[list[dict]] = None,
    point: Optional[tuple[float, float]] = None,
) -> HourRisk:
    th = thresholds[boat]
    t: datetime = row["time"]
    reasons: list[Reason] = []

    wave = row.get("wave_height")
    period = row.get("wave_period")
    wind = row.get("wind_speed")
    gust = row.get("wind_gust")
    rain = row.get("precipitation")
    code = row.get("weather_code")
    is_day = row.get("is_day")

    # Waves
    if wave is None:
        # No sea data for this hour: never call that SAFE.
        reasons.append(Reason("data_missing", None, "", None, CAUTION, "data_missing"))
    else:
        g = _graded(wave, th["wave_caution"], th["wave_unsafe"])
        if g:
            reasons.append(Reason("wave_height", round(wave, 2), "m", g[1], g[0], "wave_height"))

    # Sustained wind
    g = _graded(wind, th["wind_caution"], th["wind_unsafe"])
    if g:
        reasons.append(Reason("wind_speed", round(wind, 1), "km/h", g[1], g[0], "wind_speed"))

    # Gusts
    if gust is not None and gust >= th["gust_unsafe"]:
        reasons.append(Reason("wind_gust", round(gust, 1), "km/h", th["gust_unsafe"], UNSAFE, "wind_gust"))

    # Short, steep sea
    steep = thresholds["steep_wave_period_s"]
    if wave is not None and period is not None and period < steep and wave >= 0.7 * th["wave_caution"]:
        reasons.append(Reason("wave_period", round(period, 1), "s", steep, CAUTION, "steep_waves"))

    # Thunderstorm
    if code is not None and int(code) in thresholds["thunderstorm_codes"]:
        reasons.append(Reason("weather_code", float(code), "", None, UNSAFE, "thunderstorm"))

    # Heavy rain
    if rain is not None and rain >= thresholds["heavy_rain_mm"]:
        reasons.append(Reason("precipitation", round(rain, 1), "mm", thresholds["heavy_rain_mm"], CAUTION, "heavy_rain"))

    # Night, small boats
    if boat == "non_motorised" and is_day is not None and int(is_day) == 0:
        reasons.append(Reason("night", None, "", None, CAUTION, "night"))

    # Official warnings: always UNSAFE
    if thresholds.get("warning_overrides", True):
        for w in warnings or []:
            if not (w["starts_at"] <= t < w["expires_at"]):
                continue
            if point is not None and haversine_km(point[0], point[1], w["center_lat"], w["center_lon"]) > w["radius_km"]:
                continue
            reasons.append(
                Reason("official_warning", None, "", None, UNSAFE, "official_warning", detail=str(w.get("title", "")))
            )
            break

    # Community reports: raise to CAUTION at most, however many there are.
    radius = thresholds["report_radius_km"]
    risk_types = set(thresholds.get("risk_report_types") or [])
    relevant = []
    for r in reports or []:
        if risk_types and r["type"] not in risk_types:
            continue
        if r.get("up", 0) - r.get("down", 0) < 0:
            continue
        if not (r["created_at"] - timedelta(hours=1) <= t < r["expires_at"]):
            continue
        if point is not None and haversine_km(point[0], point[1], r["lat"], r["lon"]) > radius:
            continue
        relevant.append(r)
    if relevant:
        types = sorted({r["type"] for r in relevant})
        sea_state = sum(1 for r in relevant if r["type"] in SEA_STATE_REPORT_TYPES)
        key = "reports_rough" if sea_state >= 2 else "reports"
        reasons.append(Reason("community_reports", float(len(relevant)), "reports", 1, CAUTION, key, detail=",".join(types)))

    level = max_level(SAFE, *[r.level for r in reasons])
    reasons.sort(key=lambda r: -LEVEL_ORDER[r.level])
    return HourRisk(time=t, level=level, reasons=reasons, is_day=bool(is_day) if is_day is not None else True)


def evaluate_range(
    rows: list[dict],
    boat: str,
    thresholds: dict,
    warnings: Optional[list[dict]] = None,
    reports: Optional[list[dict]] = None,
    point: Optional[tuple[float, float]] = None,
) -> list[HourRisk]:
    return [evaluate_hour(r, boat, thresholds, warnings, reports, point) for r in rows]


def _day_hours(hours: list[HourRisk], day: date, now: Optional[datetime] = None) -> list[HourRisk]:
    """Hours on that local date. With `now`, hours that are already over are dropped."""
    out = [h for h in hours if h.time.date() == day]
    if now is not None:
        out = [h for h in out if h.time + timedelta(hours=1) > now]
    return out


def best_window(
    hours: list[HourRisk],
    day: date,
    earliest: int = 3,
    latest: int = 19,
    min_hours: int = 2,
    now: Optional[datetime] = None,
) -> Optional[dict]:
    """Longest continuous SAFE run that day between `earliest` and `latest` o'clock.

    Returns {start, end, return_by, hours} with return_by = end - 30 min, or None.
    """
    candidates = [h for h in _day_hours(hours, day, now) if earliest <= h.time.hour < latest]
    candidates.sort(key=lambda h: h.time)
    best: list[HourRisk] = []
    run: list[HourRisk] = []
    for h in candidates:
        contiguous = bool(run) and h.time - run[-1].time == timedelta(hours=1)
        if h.level == SAFE and (not run or contiguous):
            run.append(h)
        elif h.level == SAFE:
            run = [h]
        else:
            run = []
        if len(run) > len(best):
            best = list(run)
    if len(best) < min_hours:
        return None
    start = best[0].time
    if now is not None and now > start:
        start = now
    end = best[-1].time + timedelta(hours=1)
    return {"start": start, "end": end, "return_by": end - timedelta(minutes=30), "hours": len(best)}


def main_reasons(hours: list[HourRisk], limit: int = 3) -> list[Reason]:
    """The worst reason per factor across the given hours, most severe first."""
    worst: dict[str, Reason] = {}
    for h in hours:
        for r in h.reasons:
            cur = worst.get(r.factor)
            if cur is None:
                worst[r.factor] = r
                continue
            better = (LEVEL_ORDER[r.level], r.value or 0) > (LEVEL_ORDER[cur.level], cur.value or 0)
            if better:
                worst[r.factor] = r
    ranked = sorted(
        worst.values(),
        key=lambda r: (-LEVEL_ORDER[r.level], FACTOR_PRIORITY.index(r.factor) if r.factor in FACTOR_PRIORITY else 99),
    )
    return ranked[:limit]


def day_summary(
    hours: list[HourRisk],
    day: date,
    now: Optional[datetime] = None,
    earliest: int = 3,
    latest: int = 19,
    min_hours: int = 2,
) -> dict:
    """Verdict for one day.

    - any official warning that day            -> UNSAFE, no window
    - a SAFE window of >= min_hours exists      -> SAFE (go inside the window)
    - otherwise, some hour is below UNSAFE      -> CAUTION
    - otherwise                                 -> UNSAFE
    """
    considered = _day_hours(hours, day, now)
    fishing = [h for h in considered if earliest <= h.time.hour < latest]
    pool = fishing or considered
    worst = max_level(SAFE, *[h.level for h in pool]) if pool else UNSAFE
    safe_hours = sum(1 for h in fishing if h.level == SAFE)
    has_warning = any(r.factor == "official_warning" for h in considered for r in h.reasons)

    window = None if has_warning else best_window(hours, day, earliest, latest, min_hours, now)
    if not pool:
        verdict = UNSAFE
    elif has_warning:
        verdict = UNSAFE
    elif window:
        verdict = SAFE
    elif any(h.level != UNSAFE for h in pool):
        verdict = CAUTION
    else:
        verdict = UNSAFE

    return {
        "date": day,
        "verdict": verdict,
        "worst_level": worst,
        "safe_hours": safe_hours,
        "window": window,
        "reasons": main_reasons([h for h in pool if h.level != SAFE]),
    }


def best_days(hours: list[HourRisk], n_days: int = 7, now: Optional[datetime] = None) -> list[dict]:
    """Days ranked by number of SAFE daylight hours (most first)."""
    days = sorted({h.time.date() for h in hours})[:n_days]
    out = []
    for d in days:
        todays = _day_hours(hours, d, now)
        safe_daylight = sum(1 for h in todays if h.is_day and h.level == SAFE)
        summary = day_summary(hours, d, now)
        out.append({"date": d, "safe_daylight_hours": safe_daylight, "verdict": summary["verdict"], "window": summary["window"]})
    out.sort(key=lambda x: (-x["safe_daylight_hours"], x["date"]))
    return out


def confidence(hour_time: datetime, now: datetime) -> str:
    lead_hours = (hour_time - now).total_seconds() / 3600
    if lead_hours < 24:
        return "high"
    if lead_hours < 72:
        return "medium"
    return "low"


def trip_check(hours: list[HourRisk], now: datetime, planned_return: Optional[datetime] = None) -> dict:
    """Worst level between now and now+2h (not looking past the planned return)."""
    end = now + timedelta(hours=2)
    if planned_return is not None and now < planned_return < end:
        end = planned_return
    span = [h for h in hours if h.time + timedelta(hours=1) > now and h.time < end]
    if not span:
        return {"level": SAFE, "reasons": [], "hours": 0}
    level = max_level(*[h.level for h in span])
    return {"level": level, "reasons": main_reasons([h for h in span if h.level != SAFE]), "hours": len(span)}
