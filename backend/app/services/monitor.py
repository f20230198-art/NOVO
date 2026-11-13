"""Trip monitor: a background loop that checks active trips every MONITOR_INTERVAL seconds.

- past planned return + grace  -> status `overdue`, ask the fisher first, then message every
                                  contact after escalation.contact_delay_minutes (once per round)
- overdue a long time, offshore, phone silent -> AUTOMATIC SOS to every contact (escalation.auto_sos_due)
- UNSAFE within the next 2 h   -> "Head back now" push (once, re-armed when the level drops)
- scheduled trip within 1 h    -> reminder with a fresh verdict for the planned hours
- 3 AM local                   -> morning re-check push when the day's verdict changed since it was asked
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from ..config import settings
from ..db import as_utc, engine, utcnow
from ..models import Alert, ScheduledTrip, Trip, User
from ..templates import explanations as tx
from ..thresholds import THRESHOLDS
from . import advisor, escalation, forecast, notify, risk_engine

log = logging.getLogger("seasafe.monitor")

NEAR_HOME_KM = 1.0
NEAR_HOME_PING_MINUTES = 20


def _maps_link(lat: float, lon: float) -> str:
    return f"https://maps.google.com/?q={lat:.5f},{lon:.5f}"


def trip_position(trip: Trip) -> tuple[float, float]:
    if trip.last_lat is not None and trip.last_lon is not None:
        return trip.last_lat, trip.last_lon
    return trip.start_lat, trip.start_lon


def _alert_this_round(session: Session, trip: Trip, kind: str) -> Optional[Alert]:
    """An alert of this kind sent since the current planned return (adding time starts a new round)."""
    return session.exec(
        select(Alert).where(Alert.trip_id == trip.id, Alert.kind == kind, Alert.created_at > trip.planned_return)
    ).first()


def contacts_alerted(session: Session, trip: Trip) -> bool:
    """True when the family has been told about this trip (overdue this round, or an SOS)."""
    if _alert_this_round(session, trip, "overdue") is not None:
        return True
    return session.exec(
        select(Alert).where(Alert.trip_id == trip.id, Alert.kind.in_(("sos", "auto_sos")))  # type: ignore[union-attr]
    ).first() is not None


def has_track(trip: Trip) -> bool:
    """The phone reported a position at least once after the trip started."""
    return trip.last_ping_at is not None and trip.last_ping_at > trip.started_at


def last_offshore_km(trip: Trip) -> float:
    if trip.last_lat is None or trip.last_lon is None:
        return 0.0
    return risk_engine.haversine_km(trip.start_lat, trip.start_lon, trip.last_lat, trip.last_lon)


async def _handle_auto_sos(session: Session, trip: Trip, user: User, now: datetime) -> int:
    """The last step: the boat went out, is long overdue, and the phone is silent or still at sea."""
    due = escalation.auto_sos_due(
        now=now, planned_return=trip.planned_return, grace_minutes=trip.grace_minutes, boat_type=user.boat_type,
        max_offshore_km=trip.max_offshore_km, has_track=has_track(trip), last_ping_at=trip.last_ping_at,
        last_offshore_km=last_offshore_km(trip),
    )
    if not due or _alert_this_round(session, trip, "auto_sos") is not None:
        return 0
    trip.status = "emergency"
    session.add(trip)
    session.commit()

    lat, lon = trip_position(trip)
    tz = timezone(timedelta(seconds=forecast._guess_offset(trip.start_lat, trip.start_lon)))
    lang = tx.alert_lang("auto_sos", user.language)
    late = tx.fmt_duration((now - trip.planned_return).total_seconds() / 60)
    seen = trip.last_ping_at
    seen_label = (
        f"{tx.fmt_time(as_utc(seen).astimezone(tz), lang)} ({tx.fmt_duration((now - seen).total_seconds() / 60)} ago)"
        if seen else "never"
    )
    message = tx.alert_text(
        "auto_sos", lang, name=user.name, boat=tx.BOAT_WORD[tx.lang_of(lang)].get(user.boat_type, user.boat_type),
        time=tx.fmt_time(as_utc(trip.planned_return).astimezone(tz), lang), late=late, seen=seen_label,
        km=f"{max(trip.max_offshore_km or 0.0, last_offshore_km(trip)):.1f}", link=_maps_link(lat, lon),
    )
    log.warning("AUTO-SOS for trip %s (user %s): %s late", trip.id, user.id, late)
    alerts = await notify.send_to_contacts(session, user, message, "auto_sos", trip_id=trip.id)
    alerts += await notify.send_to_fisher(session, user, tx.alert_text("auto_sos_fisher", lang, late=late), "auto_sos", trip_id=trip.id)
    alerts += await notify.send_to_buddies(session, user, "buddy_sos", trip_id=trip.id, link=_maps_link(lat, lon))
    return len(alerts)


async def _scheduled_reminders(session: Session, now: datetime) -> int:
    """An hour before a scheduled departure: re-check the planned hours and tell the fisher."""
    sent = 0
    before = timedelta(minutes=int(THRESHOLDS.get("escalation", {}).get("trip_reminder_minutes_before", 60)))
    rows = session.exec(select(ScheduledTrip).where(ScheduledTrip.status == "scheduled")).all()
    for st in rows:
        if st.return_at <= now:
            st.status = "expired"
            session.add(st)
            session.commit()
            continue
        if st.reminder_sent or not (st.depart_at - before <= now < st.depart_at + timedelta(minutes=30)):
            continue
        user = session.get(User, st.user_id)
        if user is None:
            continue
        st.reminder_sent = True
        session.add(st)
        session.commit()
        try:
            ctx = await advisor.compute(session, user.home_lat, user.home_lon, user.boat_type, days=2)
        except Exception as exc:
            log.warning("trip reminder: no forecast for scheduled trip %s: %s", st.id, exc)
            continue
        level, reasons = planned_hours_level(ctx["hours"], as_utc(st.depart_at), as_utc(st.return_at))
        lang = tx.alert_lang("trip_reminder", user.language)
        words = tx.VERDICT_WORD[lang]
        extra = (
            tx.alert_text("trip_reminder_unsafe", lang, reason=tx.reason_text(reasons[0], lang) if reasons else "")
            if level == risk_engine.UNSAFE else tx.alert_text("trip_reminder_ok", lang)
        )
        message = tx.alert_text("trip_reminder", lang, time=tx.fmt_time(as_utc(st.depart_at).astimezone(ctx["tz"]), lang),
                                verdict=words[level], extra=extra)
        sent += len(await notify.send_to_fisher(session, user, message, "trip_reminder"))
    return sent


_RANK = {risk_engine.SAFE: 0, risk_engine.CAUTION: 1, risk_engine.UNSAFE: 2}


def planned_hours_level(hours, depart: datetime, ret: datetime) -> tuple[str, list]:
    """Worst engine level over [depart, return), and that level's reasons.

    No forecast hours in the range is CAUTION: unknown is never SAFE.
    """
    covered = [h for h in hours if h.time + timedelta(hours=1) > depart and h.time < ret]
    if not covered:
        return risk_engine.CAUTION, []
    worst = max(covered, key=lambda h: _RANK[h.level])
    return worst.level, list(worst.reasons)


def _near_home(trip: Trip, user: User, now: datetime) -> bool:
    if trip.last_lat is None or trip.last_lon is None or trip.last_ping_at is None:
        return False
    recent = now - trip.last_ping_at <= timedelta(minutes=NEAR_HOME_PING_MINUTES)
    return recent and risk_engine.haversine_km(trip.last_lat, trip.last_lon, user.home_lat, user.home_lon) <= NEAR_HOME_KM


async def _handle_overdue(session: Session, trip: Trip, user: User, now: datetime) -> int:
    """Two steps: ask the fisher first, then tell the contacts after a short delay.

    A forgotten "I'm back" tap is the common case, and families who get false alarms
    stop trusting the alert. The delay comes from escalation.contact_delay_minutes.
    """
    if trip.status != "overdue":
        trip.status = "overdue"
        session.add(trip)
        session.commit()
    sent = 0

    # Step 1: ask the fisher, once per round.
    if _alert_this_round(session, trip, "overdue_check") is None:
        sent += len(await notify.send_to_fisher(
            session, user, tx.alert_text("overdue_check", user.language), "overdue_check", trip_id=trip.id))

    # Step 2: the contacts, once per round.
    if _alert_this_round(session, trip, "overdue") is not None:
        return sent

    lat, lon = trip_position(trip)
    level_code, level, waves, is_night = "unknown", "unknown", "?", False
    tz = timezone(timedelta(seconds=forecast._guess_offset(trip.start_lat, trip.start_lon)))
    try:
        ctx = await advisor.compute(session, trip.start_lat, trip.start_lon, user.boat_type, days=2)
        tz = ctx["tz"]
        current = advisor.current_conditions(ctx, user.language)
        if current:
            level_code = current["level"]
            level = tx.VERDICT_WORD[tx.lang_of(user.language)][current["level"]]
            is_night = not current["is_day"]
            if current.get("wave_height") is not None:
                waves = f"{current['wave_height']:g}"
    except Exception as exc:  # the alert must go out even without a forecast
        log.warning("overdue: no sea state for trip %s: %s", trip.id, exc)

    delay = escalation.contact_delay_minutes(user.boat_type, level_code, _near_home(trip, user, now), is_night)
    delay = max(0, min(escalation.MAX_DELAY_MINUTES, int(delay)))
    overdue_since = trip.planned_return + timedelta(minutes=trip.grace_minutes)
    if now < overdue_since + timedelta(minutes=delay):
        return sent

    planned_local = as_utc(trip.planned_return).astimezone(tz)
    seen_local = as_utc(trip.last_ping_at or trip.started_at).astimezone(tz)
    message = tx.alert_text(
        "overdue_contact", user.language, name=user.name, time=tx.fmt_time(planned_local, user.language),
        seen=tx.fmt_time(seen_local, user.language), link=_maps_link(lat, lon), level=level, waves=waves,
    )
    alerts = await notify.send_to_contacts(session, user, message, "overdue", trip_id=trip.id)
    alerts += await notify.send_to_fisher(session, user, tx.alert_text("overdue_fisher", user.language), "overdue", trip_id=trip.id)
    # Buddy boats hear at the same moment as the family: the nearest help is often another fisher.
    alerts += await notify.send_to_buddies(session, user, "buddy_overdue", trip_id=trip.id,
                                           time=tx.fmt_time(planned_local, "en"), link=_maps_link(lat, lon))
    return sent + len(alerts)


async def _handle_head_back(session: Session, trip: Trip, user: User) -> int:
    lat, lon = trip_position(trip)
    try:
        ctx = await advisor.compute(session, lat, lon, user.boat_type, days=2)
    except Exception as exc:
        log.warning("head-back: no forecast for trip %s: %s", trip.id, exc)
        return 0
    check = risk_engine.trip_check(ctx["hours"], ctx["now"], as_utc(trip.planned_return))
    if check["level"] == risk_engine.UNSAFE:
        if not trip.head_back_armed:
            return 0
        reason = tx.reason_text(check["reasons"][0].to_dict(), user.language) if check["reasons"] else ""
        message = tx.alert_text("head_back", user.language, reason=reason)
        trip.head_back_armed = False
        session.add(trip)
        session.commit()
        return len(await notify.send_to_fisher(session, user, message, "head_back", trip_id=trip.id))
    if not trip.head_back_armed:  # level dropped: allow another alert if it rises again
        trip.head_back_armed = True
        session.add(trip)
        session.commit()
    return 0


async def _morning_rechecks(session: Session, now_utc: datetime) -> int:
    sent = 0
    users = session.exec(select(User).where(User.planned_day.is_not(None))).all()  # type: ignore[union-attr]
    for user in users:
        if user.recheck_sent_for == user.planned_day:
            continue
        guess = timezone(timedelta(seconds=forecast._guess_offset(user.home_lat, user.home_lon)))
        local = as_utc(now_utc).astimezone(guess)
        if local.date().isoformat() != user.planned_day or not (3 <= local.hour < 6):
            continue
        try:
            ctx = await advisor.compute(session, user.home_lat, user.home_lon, user.boat_type, days=1)
        except Exception as exc:
            log.warning("morning re-check: no forecast for user %s: %s", user.id, exc)
            continue
        verdict = ctx["days"][0]["verdict"]
        user.recheck_sent_for = user.planned_day
        session.add(user)
        session.commit()
        if user.planned_verdict and verdict != user.planned_verdict:
            words = tx.VERDICT_WORD[tx.lang_of(user.language)]
            message = tx.alert_text("morning_recheck", user.language, verdict=words[verdict], old=words[user.planned_verdict])
            sent += len(await notify.send_to_fisher(session, user, message, "morning_recheck"))
    return sent


async def tick(now: Optional[datetime] = None) -> dict:
    """One monitor pass. Returns counts, which the tests and /demo/tick use."""
    now = now or utcnow()
    result = {"checked": 0, "overdue": 0, "alerts": 0}
    with Session(engine) as session:
        # Overdue trips stay in the loop: the contacts are told a little after the fisher is asked.
        trips = session.exec(select(Trip).where(Trip.status.in_(("active", "overdue")))).all()  # type: ignore[union-attr]
        for trip in trips:
            result["checked"] += 1
            user = session.get(User, trip.user_id)
            if user is None:
                continue
            if now > trip.planned_return + timedelta(minutes=trip.grace_minutes):
                if trip.status == "active":
                    result["overdue"] += 1
                result["alerts"] += await _handle_overdue(session, trip, user, now)
                result["alerts"] += await _handle_auto_sos(session, trip, user, now)
            else:
                result["alerts"] += await _handle_head_back(session, trip, user)
        result["alerts"] += await _scheduled_reminders(session, now)
        result["alerts"] += await _morning_rechecks(session, now)
    return result


async def run_loop() -> None:
    interval = max(5, settings.monitor_interval)
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("monitor tick failed")
        await asyncio.sleep(interval)
