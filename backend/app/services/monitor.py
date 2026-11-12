"""Trip monitor: a background loop that checks active trips every MONITOR_INTERVAL seconds.

- past planned return + grace  -> status `overdue`, message every contact, push the fisher (once)
- UNSAFE within the next 2 h   -> "Head back now" push (once, re-armed when the level drops)
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
from ..models import Alert, Trip, User
from ..templates import explanations as tx
from . import advisor, forecast, notify, risk_engine

log = logging.getLogger("seasafe.monitor")


def _maps_link(lat: float, lon: float) -> str:
    return f"https://maps.google.com/?q={lat:.5f},{lon:.5f}"


def trip_position(trip: Trip) -> tuple[float, float]:
    if trip.last_lat is not None and trip.last_lon is not None:
        return trip.last_lat, trip.last_lon
    return trip.start_lat, trip.start_lon


async def _handle_overdue(session: Session, trip: Trip, user: User) -> int:
    already = session.exec(select(Alert).where(Alert.trip_id == trip.id, Alert.kind == "overdue")).first()
    trip.status = "overdue"
    session.add(trip)
    session.commit()
    if already:
        return 0

    lat, lon = trip_position(trip)
    level, waves = "unknown", "?"
    tz = timezone(timedelta(seconds=forecast._guess_offset(trip.start_lat, trip.start_lon)))
    try:
        ctx = await advisor.compute(session, trip.start_lat, trip.start_lon, user.boat_type, days=2)
        tz = ctx["tz"]
        current = advisor.current_conditions(ctx, user.language)
        if current:
            level = tx.VERDICT_WORD[tx.lang_of(user.language)][current["level"]]
            if current.get("wave_height") is not None:
                waves = f"{current['wave_height']:g}"
    except Exception as exc:  # the alert must go out even without a forecast
        log.warning("overdue: no sea state for trip %s: %s", trip.id, exc)

    planned_local = as_utc(trip.planned_return).astimezone(tz)
    message = tx.alert_text(
        "overdue_contact", user.language, name=user.name, time=tx.fmt_time(planned_local, user.language),
        link=_maps_link(lat, lon), level=level, waves=waves,
    )
    sent = await notify.send_to_contacts(session, user, message, "overdue", trip_id=trip.id)
    sent += await notify.send_to_fisher(session, user, tx.alert_text("overdue_fisher", user.language), "overdue", trip_id=trip.id)
    return len(sent)


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
        trips = session.exec(select(Trip).where(Trip.status == "active")).all()
        for trip in trips:
            result["checked"] += 1
            user = session.get(User, trip.user_id)
            if user is None:
                continue
            if now > trip.planned_return + timedelta(minutes=trip.grace_minutes):
                result["overdue"] += 1
                result["alerts"] += await _handle_overdue(session, trip, user)
            else:
                result["alerts"] += await _handle_head_back(session, trip, user)
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
