"""Tools the voice assistant may ask the server to run. The assistant proposes, the server decides.

Read tools (plan_day, get_forecast, list_trips, search) return FACTS the model may word in its own
voice, and a ready spoken sentence for the no-model path. Write tools (extend_trip, end_trip)
change the fisher's own trip and always speak in the server's words, never the model's.

Every fact here comes from the risk engine, the forecast rows, or the fisher's own rows. Nothing
in this module can set or soften a verdict: levels are copied from `risk_engine` output, and
facts keep the level CODES (SAFE/CAUTION/UNSAFE); only spoken text uses the language's word.
Everything spoken comes from assistant_text, in English or Malayalam.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from ..db import as_utc, utcnow
from ..models import ScheduledTrip, Trip, User
from ..templates import explanations as tx
from ..thresholds import THRESHOLDS
from . import advisor, drift, rag, risk_engine
from .assistant_text import COMPASS, WEEKDAYS, duration, lang_of, level as L, t
from .monitor import planned_hours_level

OPEN_STATUSES = ("active", "overdue", "emergency")
MAX_FORECAST_HOURS = 14
EXTEND_MIN, EXTEND_MAX = 15, 240

# ---- day and duration words -------------------------------------------------------

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# Malayalam weekday stems, Monday first (matched as substrings: Malayalam has no \b word edges)
_WEEKDAYS_ML = ("തിങ്കൾ", "ചൊവ്വ", "ബുധൻ", "വ്യാഴ", "വെള്ളി", "ശനി", "ഞായർ")
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "a": 1, "an": 1}
_ML_NUMBERS = {"ഒരു": 1, "ഒന്ന്": 1, "രണ്ട്": 2, "മൂന്ന്": 3, "നാല്": 4, "അഞ്ച്": 5, "ആറ്": 6}


def detect_day_index(text: str, now: datetime, n_days: int) -> int:
    """0 today ... n_days-1. Knows today/tomorrow/day after, weekday names and 'in 3 days', in
    English and Malayalam."""
    q = (text or "").lower()
    m = re.search(r"\bin (\d|one|two|three|four|five|six) days?\b", q)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _NUMBER_WORDS[m.group(1)]
        return min(n, n_days - 1)
    m = re.search(r"(\d|ഒരു|രണ്ട്|മൂന്ന്|നാല്|അഞ്ച്|ആറ്)\s*ദിവസം കഴിഞ്ഞ്", q)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _ML_NUMBERS[m.group(1)]
        return min(n, n_days - 1)
    for names in (_WEEKDAYS, _WEEKDAYS_ML):
        for i, name in enumerate(names):
            hit = re.search(rf"\b{name}\b", q) if names is _WEEKDAYS else name in q
            if hit:
                return min((i - now.weekday()) % 7, n_days - 1)
    return min(tx.detect_day(q), n_days - 1)


def parse_minutes(text: str) -> int:
    """'another hour' -> 60, 'two hours' -> 120, '45 minutes' -> 45, 'half an hour' -> 30, and the
    Malayalam 'ഒരു മണിക്കൂർ' / 'അര മണിക്കൂർ' / '45 മിനിറ്റ്'. Default 30."""
    q = (text or "").lower()
    if "half an hour" in q or "half hour" in q or "അര മണിക്കൂർ" in q:
        return 30
    m = re.search(r"(\d{1,3}|ഒരു|ഒന്ന്|രണ്ട്|മൂന്ന്|നാല്)\s*(മണിക്കൂർ|മിനിറ്റ്)", q)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _ML_NUMBERS[m.group(1)]
        return max(EXTEND_MIN, min(EXTEND_MAX, n * 60 if m.group(2) == "മണിക്കൂർ" else n))
    m = re.search(r"\b(\d{1,3}|one|two|three|four|a|an|another)\s*(hours?|hrs?|h\b|minutes?|mins?)", q)
    if not m:
        return 30
    raw = m.group(1)
    n = int(raw) if raw.isdigit() else (1 if raw == "another" else _NUMBER_WORDS.get(raw, 1))
    minutes = n * 60 if m.group(2).startswith("h") else n
    return max(EXTEND_MIN, min(EXTEND_MAX, minutes))


def day_name(now: datetime, local: datetime, lang: str = "en") -> str:
    diff = (local.date() - now.date()).days
    if diff == 0:
        return t(lang, "today")
    if diff == 1:
        return t(lang, "tomorrow")
    return t(lang, "on_weekday", weekday=WEEKDAYS[lang_of(lang)][local.weekday()])


def _num(v: Optional[float], digits: int = 1) -> Optional[float]:
    return None if v is None else round(float(v), digits)


def _ft(dt: datetime, lang: str) -> str:
    return tx.fmt_time(dt, lang)


# ---- get_forecast ------------------------------------------------------------------

def forecast_facts(ctx: dict, day_index: int, from_hour: Optional[int] = None, to_hour: Optional[int] = None,
                   lang: str = "en") -> dict:
    """Hourly sea and wind for one day, with the engine's level for each hour and the day verdict."""
    lang = lang_of(lang)
    i = max(0, min(day_index, len(ctx["days"]) - 1))
    date = ctx["dates"][i]
    day = ctx["days"][i]
    by_time = {r["time"]: r for r in ctx["rows"]}
    hours = [h for h in ctx["hours"] if h.time.date() == date and h.time + timedelta(hours=1) > ctx["now"]]
    if from_hour is not None:
        last = to_hour if to_hour is not None and to_hour >= from_hour else from_hour
        hours = [h for h in hours if from_hour <= h.time.hour <= last]
    else:
        # No hour asked: the fishing day, 4 AM to 7 PM, every hour still to come.
        hours = [h for h in hours if 4 <= h.time.hour <= 19] or hours
    # Harbour-mouth crossing: a separate estimate shown beside the verdict, never changing it.
    bar = {b["time"]: b for b in risk_engine.bar_range(ctx["rows"], ctx["boat"], THRESHOLDS)}
    out_hours = []
    for h in hours[:MAX_FORECAST_HOURS]:
        row = by_time.get(h.time, {})
        crossing = bar.get(h.time)
        out_hours.append({
            "time": _ft(h.time, lang),
            "level": h.level,
            "waves_m": _num(row.get("wave_height")),
            "wave_period_s": _num(row.get("wave_period"), 0),
            "wind_kmh": _num(row.get("wind_speed"), 0),
            "gust_kmh": _num(row.get("wind_gust"), 0),
            "wind_from": drift.compass(row.get("wind_dir")),
            "rain_mm": _num(row.get("precipitation")),
            "harbour_mouth": crossing["level"] if crossing else None,
            "reason": tx.reason_text(h.reasons[0], lang) if h.reasons else "",
        })
    w = day["window"]
    when = datetime.combine(date, datetime.min.time(), ctx["tz"])
    crossings = risk_engine.bar_windows(list(bar.values()), date, ctx["now"])
    facts = {
        "day_index": i,
        "day": day_name(ctx["now"], when, lang),
        "date": date.strftime("%A %d %B"),
        "verdict": day["verdict"],
        "safe_window": {"from": _ft(w["start"], lang), "until": _ft(w["end"], lang),
                        "return_by": _ft(w["return_by"], lang)} if w else None,
        "reasons": [r for r in (tx.reason_text(r, lang) for r in day["reasons"]) if r][:2],
        "hours": out_hours,
        "harbour_mouth_note": "Crossing the harbour mouth is judged separately from the sea verdict and never changes it.",
        "harbour_mouth_safe_crossing": [f"{_ft(c['start'], lang)} - {_ft(c['end'], lang)}" for c in crossings],
        "forecast_too_old": bool(ctx.get("too_old")),
    }
    if i == 0:
        try:
            sea = advisor.sea_out(ctx)
            facts["sea_now"] = {k: sea.get(k) for k in ("wind_from", "current_to", "current_speed", "tide_state",
                                                         "home_course", "head_wind_home", "current_against_home")}
        except Exception:  # extra detail only; the forecast answer works without it
            pass
    return facts


def forecast_levels(facts: dict) -> set[str]:
    """The verdict words a reply about these facts may use (sea levels and harbour-mouth levels)."""
    return ({facts["verdict"]} | {h["level"] for h in facts["hours"]}
            | {h["harbour_mouth"] for h in facts["hours"] if h.get("harbour_mouth")})


def _hour_sentence(h: dict, lang: str) -> str:
    parts = []
    if h["waves_m"] is not None:
        parts.append(t(lang, "fc_waves", v=f"{h['waves_m']:g}"))
    if h["wind_kmh"] is not None:
        wind = t(lang, "fc_wind", v=f"{h['wind_kmh']:g}")
        if h["gust_kmh"] is not None and h["gust_kmh"] > h["wind_kmh"]:
            wind += t(lang, "fc_gust", v=f"{h['gust_kmh']:g}")
        parts.append(wind)
    return t(lang, "fc_and").join(parts)


def forecast_spoken(ctx: dict, facts: dict, boat: str, lang: str = "en") -> str:
    """Short spoken sentences for the no-model path. Every number is copied from the facts."""
    lang = lang_of(lang)
    hours = facts["hours"]
    if not hours:
        return t(lang, "fc_no_hours", day=facts["day"])
    if len(hours) <= 2:
        h = hours[0]
        detail = _hour_sentence(h, lang)
        text = (t(lang, "fc_hour", day=facts["day"], time=h["time"], detail=detail) if detail
                else t(lang, "fc_hour_none", day=facts["day"], time=h["time"]))
        text += t(lang, "fc_hour_level", level=L(lang, h["level"]))
        if h["level"] != risk_engine.SAFE and h["reason"]:
            text += f" {h['reason']}"
        if h.get("harbour_mouth") and h["harbour_mouth"] != risk_engine.SAFE:
            text += t(lang, "fc_bar", level=L(lang, h["harbour_mouth"]))
        if facts.get("forecast_too_old"):
            text += t(lang, "fc_stale")
        elif h["level"] != risk_engine.SAFE:
            w = facts.get("safe_window")
            text += (t(lang, "fc_better", start=w["from"], end=w["until"], ret=w["return_by"]) if w
                     else t(lang, "fc_no_safe_day", day=facts["day"]))
        return text
    day = ctx["days"][facts["day_index"]]
    text = tx.answer(day, min(facts["day_index"], 2), boat, lang)
    if facts["day_index"] > 2:  # the template only knows today, tomorrow and the day after
        text = text.replace(tx.DAY_WORD[lang][2], facts["day"], 1)
    waves = [h["waves_m"] for h in hours if h["waves_m"] is not None]
    gusts = [h["gust_kmh"] for h in hours if h["gust_kmh"] is not None]
    if waves:
        lo, hi = min(waves), max(waves)
        text += (t(lang, "fc_wave_range", lo=f"{lo:g}", hi=f"{hi:g}") if hi != lo
                 else t(lang, "fc_wave_one", lo=f"{lo:g}"))
    if gusts:
        text += t(lang, "fc_gusts", v=f"{max(gusts):g}")
    return text


# ---- plan_day: when to go and when not to ----------------------------------------------
#
# The suggestion is the risk engine's own best window (a run of SAFE hours, never anything
# else). "Avoid" runs are the non-SAFE hours, with the engine's reason and the wind. Nothing
# here picks an hour on its own judgement, and stale or missing data is said out loud.

PERIODS = {
    "early morning": (3, 6), "morning": (4, 12), "afternoon": (12, 17),
    "evening": (17, 20), "tonight": (19, 24), "night": (19, 24),
}
# Malayalam part-of-day words -> the English key. Order matters: പുലർച്ചെ before രാവിലെ.
_PERIODS_ML = (("പുലർച്ചെ", "early morning"), ("രാവിലെ", "morning"), ("ഉച്ച", "afternoon"),
               ("വൈകിട്ട്", "evening"), ("വൈകുന്നേരം", "evening"), ("ഇന്ന് രാത്രി", "tonight"), ("രാത്രി", "night"))
PLAN_EARLIEST, PLAN_LATEST = 3, 21


def detect_period(text: str) -> Optional[str]:
    q = (text or "").lower()
    for name in PERIODS:  # "early morning" is checked before "morning"
        if re.search(rf"\b{name}\b", q):
            return name
    for word, name in _PERIODS_ML:
        if word in q:
            return name
    return None


def _ceil_hour(dt: datetime) -> int:
    return dt.hour + (1 if dt.minute or dt.second else 0)


def _runs(items: list[dict]) -> list[list[dict]]:
    """Consecutive non-SAFE hours grouped together."""
    runs: list[list[dict]] = []
    for it in items:
        if it["level"] == risk_engine.SAFE:
            continue
        if runs and it["_hour_index"] == runs[-1][-1]["_hour_index"] + 1:
            runs[-1].append(it)
        else:
            runs.append([it])
    return runs


def day_plan(ctx: dict, day_index: int, period: Optional[str] = None, lang: str = "en") -> dict:
    """Hour-by-hour plan for one day. Shape (also served by GET /assistant/day-plan):

    {day_index, day, date, verdict, period, lang, data: "ok" | "stale" | "missing",
     best_window: {leave_from, leave_until, return_by, start, end, return_by_at, hours} | null,
     offer: {day_index, depart_hour, return_hour, depart_label, return_label} | null,
     avoid: [{from, until, from_at, level, reason, cause, wind_kmh_max, gust_kmh_max, wind_from}],
     harbour_mouth_at_departure: level | null, harbour_mouth_safe_crossing: ["5 AM - 9 AM", ...],
     run_home: {head_wind_home, current_against_home, home_course} | null (today only),
     hours: [{time, hour, level, waves_m, wind_kmh, gust_kmh, wind_from, harbour_mouth, reason}]}
    Labels (times, day, reasons) are in `lang`; levels are always the codes SAFE/CAUTION/UNSAFE.
    """
    lang = lang_of(lang)
    i = max(0, min(day_index, len(ctx["days"]) - 1))
    date = ctx["dates"][i]
    day = ctx["days"][i]
    lo, hi = PERIODS.get(period or "", (PLAN_EARLIEST, PLAN_LATEST))
    by_time = {r["time"]: r for r in ctx["rows"]}
    bar = {b["time"]: b for b in risk_engine.bar_range(ctx["rows"], ctx["boat"], THRESHOLDS)}
    todays = sorted((h for h in ctx["hours"] if h.time.date() == date and h.time + timedelta(hours=1) > ctx["now"]
                     and lo <= h.time.hour < hi), key=lambda h: h.time)
    items = []
    for h in todays:
        row = by_time.get(h.time, {})
        crossing = bar.get(h.time)
        items.append({
            "time": _ft(h.time, lang), "hour": h.time.hour, "level": h.level,
            "waves_m": _num(row.get("wave_height")), "wind_kmh": _num(row.get("wind_speed"), 0),
            "gust_kmh": _num(row.get("wind_gust"), 0), "wind_from": drift.compass(row.get("wind_dir")),
            "harbour_mouth": crossing["level"] if crossing else None,
            "reason": tx.reason_text(h.reasons[0], lang) if h.reasons else "",
            "_factor": h.reasons[0].factor if h.reasons else "",
            "_hour_index": int(h.time.timestamp() // 3600), "_time": h.time,
        })

    stale = bool(ctx.get("too_old"))
    missing = not items or all(it["waves_m"] is None and it["wind_kmh"] is None for it in items)
    data = "stale" if stale else "missing" if missing else "ok"

    w = day["window"]
    best = offer = None
    departure_bar = None
    if w and data == "ok":  # a SAFE window only exists when the engine found SAFE hours
        best = {"leave_from": _ft(w["start"], lang), "leave_until": _ft(w["end"], lang),
                "return_by": _ft(w["return_by"], lang), "start": w["start"].isoformat(),
                "end": w["end"].isoformat(), "return_by_at": w["return_by"].isoformat(), "hours": w["hours"]}
        depart_hour, return_hour = _ceil_hour(w["start"]), w["return_by"].hour
        if depart_hour < 24 and return_hour > depart_hour:
            offer = {"day_index": i, "depart_hour": depart_hour, "return_hour": return_hour,
                     "depart_label": _ft(w["start"].replace(hour=depart_hour, minute=0, second=0, microsecond=0), lang),
                     "return_label": _ft(w["return_by"].replace(minute=0, second=0, microsecond=0), lang)}
        first = bar.get(w["start"].replace(minute=0, second=0, microsecond=0))
        departure_bar = first["level"] if first else None

    avoid = []
    for run in _runs(items):
        winds = [it["wind_kmh"] for it in run if it["wind_kmh"] is not None]
        gusts = [it["gust_kmh"] for it in run if it["gust_kmh"] is not None]
        worst = risk_engine.max_level(*[it["level"] for it in run])
        cause = next((it for it in run if it["level"] == worst and it["reason"]), run[0])
        avoid.append({
            "from": run[0]["time"], "until": _ft(run[-1]["_time"] + timedelta(hours=1), lang),
            "from_at": run[0]["_time"].isoformat(),
            "level": worst, "reason": cause["reason"],
            # What the engine blamed: only a wind or gust cause is spoken as "the wind picks up".
            "cause": cause["_factor"] or None,
            "wind_kmh_max": max(winds) if winds else None, "gust_kmh_max": max(gusts) if gusts else None,
            "wind_from": next((it["wind_from"] for it in run if it["wind_from"]), None),
        })

    run_home = None
    if i == 0:
        try:
            sea = advisor.sea_out(ctx)
            run_home = {k: sea.get(k) for k in ("head_wind_home", "current_against_home", "home_course")}
        except Exception:  # extra detail only
            run_home = None

    when = datetime.combine(date, datetime.min.time(), ctx["tz"])
    crossings = risk_engine.bar_windows(list(bar.values()), date, ctx["now"])
    return {
        "day_index": i, "day": day_name(ctx["now"], when, lang), "date": date.strftime("%A %d %B"),
        "verdict": day["verdict"], "period": period, "lang": lang, "data": data,
        "best_window": best, "offer": offer, "avoid": avoid,
        "harbour_mouth_at_departure": departure_bar,
        "harbour_mouth_safe_crossing": [f"{_ft(c['start'], lang)} - {_ft(c['end'], lang)}" for c in crossings],
        "run_home": run_home,
        "day_reasons": [r for r in (tx.reason_text(r, lang) for r in day["reasons"]) if r][:2],
        "hours": [{k: v for k, v in it.items() if not k.startswith("_")} for it in items],
    }


def plan_levels(plan: dict) -> set[str]:
    return ({plan["verdict"]} | {h["level"] for h in plan["hours"]} | {a["level"] for a in plan["avoid"]}
            | {h["harbour_mouth"] for h in plan["hours"] if h.get("harbour_mouth")})


def _wind_phrase(a: dict, lang: str = "en") -> str:
    """'the wind picks up to 30 kilometres an hour from the west', only when wind is the engine's reason."""
    if a.get("wind_kmh_max") is None or not str(a.get("cause") or "").startswith(("wind", "gust")):
        return ""
    txt = t(lang, "pl_wind", v=f"{a['wind_kmh_max']:g}")
    if a.get("wind_from"):
        txt += t(lang, "pl_wind_dir", dir=COMPASS[lang_of(lang)].get(a["wind_from"], a["wind_from"]))
    return txt


def plan_spoken(plan: dict, lang: Optional[str] = None) -> str:
    """Spoken advice for the no-model path. Every hour and level is copied from the plan."""
    lang = lang_of(lang or plan.get("lang"))
    day = plan["day"]
    period_word = t(lang, f"period_{plan['period']}") if plan["period"] else ""
    if plan["data"] == "stale":
        return t(lang, "pl_stale")
    if plan["data"] == "missing":
        return t(lang, "pl_missing", day=day, period=f" {period_word}" if period_word else "")
    best, avoid = plan["best_window"], plan["avoid"]
    parts: list[str] = []
    if plan["period"]:
        weekday_form = lang == "en" and day.startswith("on ")
        label = t(lang, "pl_label_weekday" if weekday_form else "pl_label", day=day, period=period_word)
        if not avoid:
            waves = [h["waves_m"] for h in plan["hours"] if h["waves_m"] is not None]
            parts.append(t(lang, "pl_period_safe", label=label, level=L(lang, risk_engine.SAFE),
                           waves=t(lang, "pl_period_waves", v=f"{max(waves):g}") if waves else ""))
        else:
            a = avoid[0]
            why = _wind_phrase(a, lang) or a["reason"].rstrip(".")
            parts.append(t(lang, "pl_period_level", label=label, level=L(lang, a["level"]), start=a["from"],
                           why=f", {why}" if why else ""))
    if best:
        if not plan["period"] or avoid:
            key = "pl_best" if plan["period"] else "pl_go"
            parts.append(t(lang, key, day=day, start=best["leave_from"], end=best["leave_until"], ret=best["return_by"]))
        end = datetime.fromisoformat(best["end"])
        later = None if plan["period"] else next(
            (a for a in avoid if datetime.fromisoformat(a["from_at"]) >= end), None)
        if later:
            why = _wind_phrase(later, lang) or later["reason"].rstrip(".")
            if lang == "en":
                why = why.lower()
            parts.append(t(lang, "pl_avoid", start=later["from"], level=L(lang, later["level"]),
                           why=f", {why}" if why else ""))
        if plan["harbour_mouth_at_departure"] and plan["harbour_mouth_at_departure"] != risk_engine.SAFE:
            parts.append(t(lang, "pl_bar", level=L(lang, plan["harbour_mouth_at_departure"])))
        if plan["offer"]:
            parts.append(t(lang, "pl_offer", dep=plan["offer"]["depart_label"], ret=plan["offer"]["return_label"]))
    elif not plan["period"] or avoid:
        reason = plan["day_reasons"][0] if plan["day_reasons"] else ""
        parts.append(t(lang, "pl_no_go", day=day, reason=reason).strip())
    return " ".join(parts)


# ---- trips --------------------------------------------------------------------------

def open_trip(session: Session, user: User) -> Optional[Trip]:
    return session.exec(
        select(Trip).where(Trip.user_id == user.id, Trip.status.in_(OPEN_STATUSES)).order_by(Trip.id.desc())  # type: ignore[union-attr]
    ).first()


def _local(dt: datetime, ctx: dict) -> datetime:
    return as_utc(dt).astimezone(ctx["tz"])


def _at(dt: datetime, ctx: dict, lang: str = "en") -> str:
    local = _local(dt, ctx)
    return t(lang, "at", day=day_name(ctx["now"], local, lang), time=_ft(local, lang))


def trips_facts(session: Session, user: User, ctx: dict, now: Optional[datetime] = None, lang: str = "en") -> dict:
    """Only this fisher's own trips."""
    lang = lang_of(lang)
    now = now or utcnow()
    active = open_trip(session, user)
    upcoming = session.exec(
        select(ScheduledTrip).where(ScheduledTrip.user_id == user.id, ScheduledTrip.status.in_(("proposed", "scheduled")),  # type: ignore[union-attr]
                                    ScheduledTrip.return_at > now).order_by(ScheduledTrip.depart_at)  # type: ignore[arg-type]
    ).all()
    last = session.exec(
        select(Trip).where(Trip.user_id == user.id, Trip.status == "returned").order_by(Trip.id.desc())  # type: ignore[union-attr]
    ).first()
    return {
        "at_sea_now": {"status": active.status, "started": _at(active.started_at, ctx, lang),
                       "return_time": _at(active.planned_return, ctx, lang)} if active else None,
        "scheduled": [{"status": t(lang, "waiting_yes") if s.status == "proposed" else t(lang, "scheduled"),
                       "proposed": s.status == "proposed",
                       "leave": _at(s.depart_at, ctx, lang), "back_by": _ft(_local(s.return_at, ctx), lang),
                       "sea_when_planned": s.verdict} for s in upcoming],
        "last_trip": {"started": _at(last.started_at, ctx, lang),
                      "ended": _at(last.ended_at, ctx, lang) if last.ended_at else None} if last else None,
    }


def trips_spoken(facts: dict, lang: str = "en") -> str:
    parts = []
    sea = facts["at_sea_now"]
    if sea:
        late = t(lang, "tr_overdue") if sea["status"] == "overdue" else ""
        parts.append(t(lang, "tr_at_sea", ret=sea["return_time"]) + late)
    sched = facts["scheduled"]
    if sched:
        first = sched[0]
        if len(sched) == 1:
            parts.append(t(lang, "tr_one", leave=first["leave"], back=first["back_by"]))
        else:
            parts.append(t(lang, "tr_many", n=len(sched), leave=first["leave"]))
        if any(s["proposed"] for s in sched):
            parts.append(t(lang, "tr_waiting"))
    if not sea and not sched:
        parts.append(t(lang, "tr_none"))
        if facts["last_trip"] and facts["last_trip"]["ended"]:
            parts.append(t(lang, "tr_last", when=facts["last_trip"]["ended"]))
        parts.append(t(lang, "tr_shall"))
    return " ".join(parts)


async def extend_trip(session: Session, user: User, ctx: dict, minutes: int, lang: str = "en") -> tuple[str, Optional[Trip]]:
    """'More time' by voice. Same effect as the button, plus the engine's view of the extra hours.

    The extension is always granted: refusing it would not bring the boat back, it would only
    wake the family early while the fisher believes they have more time. If the extra hours are
    rough, the reply says so plainly so the fisher heads back.
    """
    from ..routers import trips as trips_router  # late import: routers import services

    trip = open_trip(session, user)
    if trip is None or trip.status not in ("active", "overdue"):
        return t(lang, "ext_no_trip"), None
    minutes = max(EXTEND_MIN, min(EXTEND_MAX, minutes))
    old_return = as_utc(trip.planned_return)
    await trips_router.extend_trip(trip.id, trips_router.ExtendIn(minutes=minutes), user=user, session=session)
    session.refresh(trip)
    new_return = as_utc(trip.planned_return)
    sea, reasons = planned_hours_level(ctx["hours"], max(old_return, as_utc(utcnow())), new_return)
    text = t(lang, "ext_done", dur=duration(lang, minutes), time=_ft(_local(trip.planned_return, ctx), lang))
    if sea == risk_engine.UNSAFE:
        why = tx.reason_text(reasons[0], lang) if reasons else ""
        text += t(lang, "ext_unsafe", level=L(lang, sea), why=why)
    elif sea == risk_engine.CAUTION:
        text += t(lang, "ext_caution", level=L(lang, sea))
    return re.sub(r"\s{2,}", " ", text).strip(), trip


def end_trip_question(session: Session, user: User, ctx: dict, lang: str = "en") -> tuple[str, Optional[Trip]]:
    """Ending a trip stops the watch, so it is asked back before it is done."""
    trip = open_trip(session, user)
    if trip is None:
        return t(lang, "end_no_trip"), None
    return t(lang, "end_ask"), trip


async def end_trip(session: Session, user: User, trip_id: int, lang: str = "en") -> tuple[str, Optional[Trip]]:
    from ..routers import trips as trips_router

    trip = session.get(Trip, trip_id)
    if trip is None or trip.user_id != user.id or trip.status not in OPEN_STATUSES:
        return t(lang, "end_already"), None
    await trips_router.end_trip(trip.id, user=user, session=session)
    session.refresh(trip)
    return t(lang, "end_done"), trip


# ---- search (retrieval over the app's own public data and community posts) -------------

def search_docs(session: Session, user: User, query: str, now: Optional[datetime] = None) -> list[rag.Doc]:
    return rag.research(session, user, query, now=now)


def search_spoken(docs: list[rag.Doc], lang: str = "en") -> str:
    """No-model answer: only trusted text is ever read out. Posts by other people are counted,
    not quoted, because nobody has checked them."""
    trusted, untrusted = rag.split_trust(docs)
    best = [d for d in trusted if d.id.startswith(("kb:", "warning:", "me:"))][:1]
    text = " ".join(rag.doc_text(d, lang) for d in best)
    if untrusted:
        n = len(untrusted)
        text += t(lang, "search_posts", n=n, verb="is" if n == 1 else "are", s="" if n == 1 else "s")
    return text.strip()
