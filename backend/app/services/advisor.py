"""Ask the Sea: run the risk engine, then have Claude (or a template) explain the result.

The verdict, window and return-by time always come from risk_engine. Claude only chooses
which day the question is about and words the explanation. If its wording disagrees with
the engine's verdict, the deterministic template is used instead.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session

from ..config import settings
from ..templates import explanations as tx
from ..thresholds import THRESHOLDS
from . import community, drift, forecast, llm, risk_engine
from .risk_engine import HourRisk

log = logging.getLogger("seasafe.advisor")

MODEL = "claude-opus-5-5"
AI_TIMEOUT_S = 10.0  # a fisher holding a phone will not wait longer; the template answers instantly

SYSTEM_PROMPT = """You are the voice of Sea Safe, a sea-safety assistant for small-scale fishers. Your reply is \
read aloud on a phone to a fisher deciding whether to take their boat out, so it has to be short, plain and \
exactly faithful to the data.

A separate rule-based risk engine has already decided everything that matters: the verdict for each day \
(SAFE, CAUTION or UNSAFE), the safe time window, the return-by time, and the reasons with their numbers. \
Lives depend on those verdicts being reported unchanged. Your job is only to explain them. Use only the \
numbers and times in the data you are given; never estimate, round differently, or add figures of your own, \
and never soften or strengthen a verdict.

Pick the day the fisher is asking about (day_index 0 = today, 1 = tomorrow, 2 = the day after; use 0 if they \
do not say). If they name a specific departure hour, put it in start_hour as a 24-hour number, otherwise null.

Write `answer` as 2 to 4 short sentences in the requested language. State that day's verdict using the exact \
verdict word listed for the language, then the safe window and the return-by time if there is one, then the \
main reason with its numbers. If the verdict is UNSAFE, tell them clearly not to go. If the day has a safe \
window but a specific hour they asked about is worse, say so. Mention official warnings and nearby fisher \
reports when present. Say the times exactly as they are written in safe_window and return_by, and give each reason in the words \
of its text. Use everyday words a fisher would use, no technical jargon, and never mention field names or \
level codes from the data. End `answer` with the \
advisory line given for the language, word for word.

Write `short_answer` in the same language, under 12 words: the verdict word and the single most useful fact. \
It is shown on a small card.

If the question is not about going to sea, answer it in one brief sentence and then give today's sea verdict \
as above."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "day_index": {"type": "integer", "enum": [0, 1, 2]},
        "start_hour": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "answer": {"type": "string"},
        "short_answer": {"type": "string"},
    },
    "required": ["day_index", "start_hour", "answer", "short_answer"],
    "additionalProperties": False,
}

LANGUAGE_NAMES = {"en": "English", "ml": "Malayalam", "ta": "Tamil", "hi": "Hindi", "ar": "Arabic"}

# Keyword test for step 4: does the wording agree with the engine's verdict?
_MUST_HAVE = {
    "en": {"SAFE": ["safe"], "CAUTION": ["caution", "careful"], "UNSAFE": ["unsafe", "not safe", "dangerous", "do not go", "don't go"]},
    "ml": {"SAFE": ["സുരക്ഷിത"], "CAUTION": ["ജാഗ്രത"], "UNSAFE": ["അപകട", "പോകരുത്"]},
}
_EN_BARE_SAFE = re.compile(r"(?<!un)(?<!not )(?<!no )(?<!n't )\bsafe\b")
_DO_NOT_GO = {"en": ["do not go", "don't go"], "ml": ["പോകരുത്"]}


def contradicts(answer: str, verdict: str, language: str) -> bool:
    """True when the text does not match the engine verdict. Unknown languages are not checked."""
    if language not in _MUST_HAVE:
        return False
    text = answer.lower()
    if not any(k in text for k in _MUST_HAVE[language][verdict]):
        return True
    if verdict == "SAFE":
        if language == "en" and not _EN_BARE_SAFE.search(text):
            return True  # only "unsafe" / "not safe" was said
        if language == "ml" and "സുരക്ഷിതമല്ല" in text:
            return True  # "not safe"
        return any(k in text for k in _DO_NOT_GO[language])
    if language == "en":
        return bool(_EN_BARE_SAFE.search(text))
    return "സുരക്ഷിതം" in text or "സുരക്ഷിതമാണ്" in text


def misses_return_time(answer: str, window: Optional[dict]) -> bool:
    """True when there is a return-by time and the text does not state it.

    The verdict word alone is not enough: a wrong return time is as dangerous as a wrong
    verdict. Accepts 24-hour ("13:30") and 12-hour ("1:30", "1.30") spellings.
    """
    if not window:
        return False
    rb: datetime = window["return_by"]
    h12 = rb.hour % 12 or 12
    spellings = {f"{rb.hour}:{rb.minute:02d}", f"{rb.hour:02d}:{rb.minute:02d}", f"{h12}:{rb.minute:02d}", f"{h12}.{rb.minute:02d}"}
    if rb.minute == 0:
        return re.search(rf"(?<![\d:.]){h12}(?![\d:.])|(?<![\d:.]){rb.hour}(?![\d:.])", answer) is None
    return not any(s in answer for s in spellings)


async def compute(session: Session, lat: float, lon: float, boat: str, days: int = 3) -> dict:
    """Forecast + risk engine for the next `days` local days. Raises ForecastUnavailable."""
    fc = await forecast.get_forecast(lat, lon)
    tz = timezone(timedelta(seconds=fc["utc_offset_seconds"]))
    now = datetime.now(tz)
    dates = [(now + timedelta(days=i)).date() for i in range(days)]
    rows = [r for r in fc["rows"] if r["time"].date() in dates]

    warnings = community.active_warnings(session, lat, lon, include_upcoming_hours=days * 24)
    reports = [r for r, _ in community.nearby_reports(session, lat, lon, THRESHOLDS["report_radius_km"])]
    # A forecast that could not be refreshed for too long is treated as unknown, not as calm.
    too_old = bool(fc.get("stale")) and fc.get("age_minutes", 0) > THRESHOLDS.get("stale_forecast_minutes", 180)
    hours = risk_engine.evaluate_range(
        rows, boat, THRESHOLDS,
        [community.warning_for_engine(w) for w in warnings],
        [community.report_for_engine(r) for r in reports],
        point=(lat, lon),
        data_stale=too_old,
    )
    summaries = [risk_engine.day_summary(hours, d, now) for d in dates]
    return {
        "fc": fc, "tz": tz, "now": now, "dates": dates, "rows": rows, "hours": hours, "days": summaries,
        "warnings": warnings, "reports": reports, "boat": boat, "lat": lat, "lon": lon, "too_old": too_old,
    }


def _reason_out(reason: risk_engine.Reason, language: str) -> dict:
    d = reason.to_dict()
    d["text"] = tx.reason_text(d, language)
    return d


def _window_out(window: Optional[dict], language: str) -> Optional[dict]:
    if not window:
        return None
    return {
        "start": window["start"].isoformat(),
        "end": window["end"].isoformat(),
        "return_by": window["return_by"].isoformat(),
        "start_label": tx.fmt_time(window["start"], language),
        "end_label": tx.fmt_time(window["end"], language),
        "return_by_label": tx.fmt_time(window["return_by"], language),
        "hours": window["hours"],
    }


def _day_confidence(ctx: dict, i: int) -> str:
    day = ctx["days"][i]
    ref = day["window"]["start"] if day["window"] else datetime.combine(ctx["dates"][i], datetime.min.time(), ctx["tz"]).replace(hour=12)
    return risk_engine.confidence(max(ref, ctx["now"]), ctx["now"])


def _day_out(ctx: dict, i: int, language: str) -> dict:
    day = ctx["days"][i]
    return {
        "day_index": i,
        "date": day["date"].isoformat(),
        "verdict": day["verdict"],
        "verdict_word": tx.VERDICT_WORD[tx.lang_of(language)][day["verdict"]],
        "worst_level": day["worst_level"],
        "safe_hours": day["safe_hours"],
        "window": _window_out(day["window"], language),
        "return_by": day["window"]["return_by"].isoformat() if day["window"] else None,
        "confidence": _day_confidence(ctx, i),
        "reasons": [_reason_out(r, language) for r in day["reasons"]],
        "short_answer": tx.short_answer(day, language),
    }


def _hourly_out(ctx: dict, language: str) -> list[dict]:
    by_time = {r["time"]: r for r in ctx["rows"]}
    out = []
    for h in ctx["hours"]:
        row = by_time.get(h.time, {})
        out.append(
            {
                "time": h.time.isoformat(),
                "day_index": ctx["dates"].index(h.time.date()),
                "hour": h.time.hour,
                "level": h.level,
                "is_day": h.is_day,
                "past": h.time + timedelta(hours=1) <= ctx["now"],
                "wave_height": row.get("wave_height"),
                "wave_period": row.get("wave_period"),
                "wind_speed": row.get("wind_speed"),
                "wind_gust": row.get("wind_gust"),
                "wind_from": drift.compass(row.get("wind_dir")),
                "wind_from_deg": row.get("wind_dir"),
                "current_to_deg": row.get("current_dir"),
                "current_speed": row.get("current_speed"),
                "current_to": drift.compass(row.get("current_dir")),
                "tide_m": row.get("sea_level"),
                "reasons": [_reason_out(r, language) for r in h.reasons],
            }
        )
    return out


def sea_out(ctx: dict) -> dict:
    """Wind, current, tide and depth for the hour in progress, and what they mean for the run
    home: the head wind and the current against a boat steering from the sea point back to
    the harbour. Information only; it does not change the verdict."""
    fc, now = ctx["fc"], ctx["now"]
    ordered = sorted(ctx["rows"], key=lambda r: r["time"])
    i = next((k for k, r in enumerate(ordered) if r["time"] <= now < r["time"] + timedelta(hours=1)), None)
    row = ordered[i] if i is not None else {}
    nxt = ordered[i + 1] if i is not None and i + 1 < len(ordered) else {}
    course = None
    if risk_engine.haversine_km(fc["sea_lat"], fc["sea_lon"], ctx["lat"], ctx["lon"]) > 0.5:
        course = drift.bearing(fc["sea_lat"], fc["sea_lon"], ctx["lat"], ctx["lon"])
    tide_state = None
    if row.get("sea_level") is not None and nxt.get("sea_level") is not None:
        change = nxt["sea_level"] - row["sea_level"]
        tide_state = "rising" if change > 0.02 else "falling" if change < -0.02 else "slack"
    return {
        "wind_speed": row.get("wind_speed"),
        "wind_gust": row.get("wind_gust"),
        "wind_from_deg": row.get("wind_dir"),
        "wind_from": drift.compass(row.get("wind_dir")),
        "current_speed": row.get("current_speed"),
        "current_to_deg": row.get("current_dir"),
        "current_to": drift.compass(row.get("current_dir")),
        "tide_m": row.get("sea_level"),
        "tide_state": tide_state,
        "depth_m": fc.get("depth_m"),
        "wave_height": row.get("wave_height"),
        "wave_period": row.get("wave_period"),
        "swell_height": row.get("swell_wave_height"),
        # The run home, from the sea point to the harbour.
        "home_course_deg": round(course) if course is not None else None,
        "home_course": drift.compass(course),
        "head_wind_home": drift.head_wind(row.get("wind_speed"), row.get("wind_dir"), course),
        "current_against_home": drift.against_current(row.get("current_speed"), row.get("current_dir"), course),
    }


def harbour_mouth_out(ctx: dict, language: str) -> dict:
    """Harbour-mouth crossing estimate for the home screen: level now, hourly strip, and the
    open crossing windows for each day. Shown beside the verdict; it never changes it."""
    bar = risk_engine.bar_range(ctx["rows"], ctx["boat"], THRESHOLDS)
    now = ctx["now"]
    current = next((b for b in bar if b["time"] <= now < b["time"] + timedelta(hours=1)), None)
    days = []
    for i, d in enumerate(ctx["dates"]):
        windows = risk_engine.bar_windows(bar, d, now)
        todays = [b for b in bar if b["time"].date() == d and b["time"] + timedelta(hours=1) > now and 3 <= b["time"].hour < 19]
        worst = risk_engine.max_level(risk_engine.SAFE, *[b["level"] for b in todays]) if todays else risk_engine.CAUTION
        days.append({
            "day_index": i,
            "date": d.isoformat(),
            "worst_level": worst,
            "windows": [
                {"start": w["start"].isoformat(), "end": w["end"].isoformat(), "hours": w["hours"],
                 "start_label": tx.fmt_time(w["start"], language), "end_label": tx.fmt_time(w["end"], language)}
                for w in windows
            ],
        })
    # When the bar next stops being SAFE to cross, so the fisher knows when to be back inside.
    closes = None
    if current and current["level"] == risk_engine.SAFE:
        for b in bar:
            if b["time"] > now and b["level"] != risk_engine.SAFE:
                closes = b["time"]
                break
    return {
        "level": current["level"] if current else risk_engine.CAUTION,
        "breaker_m": current["breaker_m"] if current else None,
        "ebb": bool(current and current["ebb"]),
        "long_swell": bool(current and current["long_swell"]),
        "closes_at": closes.isoformat() if closes else None,
        "closes_label": tx.fmt_time(closes, language) if closes else None,
        "days": days,
        "hourly": [
            {"time": b["time"].isoformat(), "day_index": ctx["dates"].index(b["time"].date()), "hour": b["time"].hour,
             "level": b["level"], "breaker_m": b["breaker_m"], "ebb": b["ebb"],
             "past": b["time"] + timedelta(hours=1) <= now}
            for b in bar
        ],
    }


def current_conditions(ctx: dict, language: str = "en") -> Optional[dict]:
    """The hour slot that contains `now`."""
    for item in _hourly_out(ctx, language):
        t = datetime.fromisoformat(item["time"])
        if t <= ctx["now"] < t + timedelta(hours=1):
            return item
    return None


def forecast_payload(ctx: dict, language: str, session: Session) -> dict:
    """What the home screen needs: day summaries, hourly strip, warnings, reports. No LLM."""
    fc = ctx["fc"]
    best = risk_engine.best_days(
        risk_engine.evaluate_range(
            fc["rows"], ctx["boat"], THRESHOLDS,
            [community.warning_for_engine(w) for w in ctx["warnings"]],
            [community.report_for_engine(r) for r in ctx["reports"]],
            point=(ctx["lat"], ctx["lon"]),
            data_stale=ctx.get("too_old", False),
        ),
        n_days=7, now=ctx["now"],
    )
    return {
        "boat_type": ctx["boat"],
        "language": language,
        "location": {"lat": ctx["lat"], "lon": ctx["lon"], "sea_lat": fc["sea_lat"], "sea_lon": fc["sea_lon"]},
        "generated_at": ctx["now"].isoformat(),
        "fetched_at": fc["fetched_at"].isoformat(),
        "utc_offset_seconds": fc["utc_offset_seconds"],
        "stale": bool(fc.get("stale")),
        "age_minutes": fc.get("age_minutes", 0),
        "scenario": fc.get("scenario", "real"),
        "days": [_day_out(ctx, i, language) for i in range(len(ctx["days"]))],
        "hourly": _hourly_out(ctx, language),
        "current": current_conditions(ctx, language),
        "harbour_mouth": harbour_mouth_out(ctx, language),
        "sea": sea_out(ctx),
        "best_days": [
            {"date": b["date"].isoformat(), "safe_daylight_hours": b["safe_daylight_hours"], "verdict": b["verdict"]}
            for b in best
        ],
        "warnings": [community.warning_out(w) for w in ctx["warnings"]],
        "reports_nearby": [community.report_out(session, r) for r in ctx["reports"]],
        "advisory": tx.ADVISORY[tx.lang_of(language)],
    }


def _level_ranges(hours: list[HourRisk]) -> str:
    """'00-05 CAUTION, 06-10 SAFE, 11-23 UNSAFE' for one day's hours."""
    parts: list[str] = []
    start = prev = None
    level = None
    for h in sorted(hours, key=lambda x: x.time):
        if level == h.level and prev is not None and h.time.hour == prev + 1:
            prev = h.time.hour
            continue
        if level is not None:
            parts.append(f"{start:02d}-{prev:02d} {level}")
        start = prev = h.time.hour
        level = h.level
    if level is not None:
        parts.append(f"{start:02d}-{prev:02d} {level}")
    return ", ".join(parts)


def _prompt_data(ctx: dict, question: str, language: str, location_name: str) -> str:
    lang = tx.lang_of(language)
    data = {
        "question": question,
        "reply_language": LANGUAGE_NAMES.get(language, "English"),
        "verdict_words_to_use": tx.VERDICT_WORD[lang],
        "advisory_line": tx.ADVISORY[lang],
        "boat_type": ctx["boat"],
        "location": location_name or f"{ctx['lat']:.3f}, {ctx['lon']:.3f}",
        "local_time_now": ctx["now"].strftime("%Y-%m-%d %H:%M"),
        "days": engine_days(ctx, lang),
        "official_warnings": [{"title": w.title, "message": w.message, "source": w.source} for w in ctx["warnings"]],
        "fisher_reports_nearby": [{"type": r.type, "note": r.note, "up": r.up, "down": r.down} for r in ctx["reports"]],
    }
    return json.dumps(data, ensure_ascii=False)


def engine_days(ctx: dict, lang: str) -> list[dict]:
    """The risk engine's per-day facts, worded for the model to repeat rather than reinterpret."""
    days = []
    for i, day in enumerate(ctx["days"]):
        d = ctx["dates"][i]
        todays = [h for h in ctx["hours"] if h.time.date() == d]
        rows = [r for r in ctx["rows"] if r["time"].date() == d]
        waves = [r["wave_height"] for r in rows if r.get("wave_height") is not None]
        gusts = [r["wind_gust"] for r in rows if r.get("wind_gust") is not None]
        w = day["window"]
        days.append(
            {
                "day_index": i,
                "date": d.isoformat(),
                "weekday": d.strftime("%A"),
                "verdict": day["verdict"],
                # Times and reasons are given already worded in the fisher's language, so the
                # model repeats them instead of inventing its own format or quoting field names.
                "safe_window": {"from": tx.fmt_time(w["start"], lang), "until": tx.fmt_time(w["end"], lang)} if w else None,
                "return_by": tx.fmt_time(w["return_by"], lang) if w else None,
                "reasons_apply_to": "the hours outside the safe window" if w else "the whole day",
                "confidence": _day_confidence(ctx, i),
                "reasons": [{"level": r.level, "text": tx.reason_text(r, lang)} for r in day["reasons"]],
                "hourly_levels_24h": _level_ranges(todays),
                "wave_height_m_min_max": [min(waves), max(waves)] if waves else None,
                "wind_gust_kmh_max": max(gusts) if gusts else None,
            }
        )
    return days


async def _ask_claude(ctx: dict, question: str, language: str, location_name: str) -> Optional[dict]:
    """One Claude call. Returns the parsed JSON, or None on any failure."""
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=AI_TIMEOUT_S, max_retries=0)
        response = await asyncio.wait_for(
            client.beta.messages.create(
                model=MODEL,
                max_tokens=4000,
                # If a safety classifier declines, the API re-runs the request on a fallback model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=SYSTEM_PROMPT,
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
                messages=[{"role": "user", "content": _prompt_data(ctx, question, language, location_name)}],
            ),
            timeout=AI_TIMEOUT_S,
        )
        if response.stop_reason in ("refusal", "max_tokens"):
            log.warning("advisor: model stopped with %s", response.stop_reason)
            return None
        text = next((b.text for b in response.content if b.type == "text"), "")
        data = json.loads(text)
        if data.get("day_index") not in (0, 1, 2) or not str(data.get("answer") or "").strip():
            return None
        return data
    except asyncio.TimeoutError:
        log.warning("advisor: Claude call timed out")
    except anthropic.RateLimitError:
        log.warning("advisor: rate limited")
    except anthropic.APIStatusError as exc:
        log.warning("advisor: API error %s: %s", exc.status_code, exc.message)
    except anthropic.APIConnectionError:
        log.warning("advisor: network error reaching Claude")
    except Exception as exc:  # the demo must never break because of the LLM
        log.warning("advisor: unexpected error: %s", exc)
    return None


JSON_INSTRUCTION = (
    "\n\nReply with one JSON object and nothing else, with exactly these keys: "
    '"day_index" (0, 1 or 2), "start_hour" (a number from 0 to 23, or null), '
    '"answer" (string), "short_answer" (string).'
)


def llm_provider() -> str:
    """Which model words the answer: "claude", "pool" (rotating Groq/Gemini keys), or "" for templates."""
    if settings.anthropic_api_key:
        return "claude"
    if llm.available():
        return "pool"
    return ""


def provider_label() -> str:
    p = llm_provider()
    if p == "pool":
        return f"{len(llm.pool())} rotating key(s): " + ", ".join(k.label for k in llm.pool().keys)
    return p


async def _ask_pool(ctx: dict, question: str, language: str, location_name: str) -> Optional[dict]:
    """One call through the rotating key pool. The full context goes with every attempt."""
    try:
        data = await llm.chat_json(
            [
                {"role": "system", "content": SYSTEM_PROMPT + JSON_INSTRUCTION},
                {"role": "user", "content": _prompt_data(ctx, question, language, location_name)},
            ],
            deadline_s=AI_TIMEOUT_S,
        )
    except Exception as exc:  # the demo must never break because of the LLM
        log.warning("advisor: pool call failed: %s", exc)
        return None
    if not data or data.get("day_index") not in (0, 1, 2) or not str(data.get("answer") or "").strip():
        return None
    return data


async def _ask_llm(ctx: dict, question: str, language: str, location_name: str) -> Optional[dict]:
    provider = llm_provider()
    if provider == "claude":
        return await _ask_claude(ctx, question, language, location_name)
    if provider == "pool":
        return await _ask_pool(ctx, question, language, location_name)
    return None


async def ask(session: Session, question: str, language: str, lat: float, lon: float, boat: str, location_name: str = "") -> dict:
    ctx = await compute(session, lat, lon, boat, days=3)
    payload = forecast_payload(ctx, language, session)

    source = "template"
    start_hour = None
    ai = await _ask_llm(ctx, question, language, location_name)
    if ai is not None:
        day_index = min(ai["day_index"], len(ctx["days"]) - 1)
        verdict = ctx["days"][day_index]["verdict"]
        if contradicts(ai["answer"], verdict, language):
            log.warning("advisor: model answer contradicts engine verdict %s, using template", verdict)
            ai = None
        elif verdict == "SAFE" and misses_return_time(ai["answer"], ctx["days"][day_index]["window"]):
            log.warning("advisor: model answer leaves out or changes the return-by time, using template")
            ai = None
        else:
            source = "ai"
            answer_text = ai["answer"].strip()
            short = (ai.get("short_answer") or "").strip() or tx.short_answer(ctx["days"][day_index], language)
            sh = ai.get("start_hour")
            start_hour = sh if isinstance(sh, int) and 0 <= sh <= 23 else None
    if ai is None:
        day_index = min(tx.detect_day(question), len(ctx["days"]) - 1)
        answer_text = tx.answer(ctx["days"][day_index], day_index, boat, language)
        short = tx.short_answer(ctx["days"][day_index], language)

    day = payload["days"][day_index]
    asked_hour = None
    if start_hour is not None:
        asked_hour = next((h for h in payload["hourly"] if h["day_index"] == day_index and h["hour"] == start_hour), None)

    return {
        **payload,
        "question": question,
        "day_index": day_index,
        "date": day["date"],
        "verdict": day["verdict"],  # always the engine's verdict
        "verdict_word": day["verdict_word"],
        "window": day["window"],
        "return_by": day["return_by"],
        "confidence": day["confidence"],
        "reasons": day["reasons"],
        "answer": answer_text,
        "short_answer": short,
        "start_hour": start_hour,
        "asked_hour": asked_hour,
        "source": source,
    }
