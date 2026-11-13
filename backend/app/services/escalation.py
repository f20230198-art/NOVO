"""Overdue escalation: when the fisher is asked, when the family is told, when SOS goes out.

Timeline for one trip (every step moves back when the fisher adds time):

    planned_return + grace                      -> ask the fisher "Are you back?"
      + contact_delay_minutes(...)              -> tell the emergency contacts
    planned_return + grace + auto_sos_minutes   -> AUTOMATIC SOS, only if the boat went offshore
                                                   AND the phone is silent or still at sea

The auto-SOS delay is long on purpose (1.5-3 h after the trip is overdue, by boat type).
Fishing trips often run late, and a false SOS costs the family a terrible few hours and
wears down trust in the alert. A real emergency is already reported to the family at the
contacts step, so auto-SOS adds the rescue wording and the last known position.

Everything here is pure (no database, no clock) so it is unit-tested directly.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from ..thresholds import THRESHOLDS

MAX_DELAY_MINUTES = 30


def contact_delay_minutes(boat_type: str, sea_level: str, near_home: bool, is_night: bool) -> int:
    """Minutes between asking the fisher and alerting the contacts.

    boat_type  "non_motorised" | "motorised" | "mechanised"
    sea_level  "SAFE" | "CAUTION" | "UNSAFE" | "unknown" (sea state at the boat right now)
    near_home  the last position ping was recent and within 1 km of the home harbour
    is_night   it is dark at the boat's position
    """
    # UNSAFE sea: tell the family at once, even near home. Harbour-mouth crossings in rough sea
    # are where many boats capsize, within sight of the shore.
    if sea_level == "UNSAFE":
        return 0
    # Otherwise a recent ping from the harbour almost always means a forgotten "I'm back" tap:
    # give the fisher the longest chance to answer before worrying the family.
    if near_home:
        return MAX_DELAY_MINUTES
    delay = 15
    if sea_level in ("CAUTION", "unknown"):
        delay = 10  # unknown is never treated as calm
    if is_night:
        delay = min(delay, 5)
    if boat_type == "non_motorised":
        delay = min(delay, 10)  # small boats drift and swamp fastest
    return delay


def _cfg() -> dict:
    return THRESHOLDS.get("escalation", {})


def auto_sos_minutes(boat_type: str) -> int:
    table = _cfg().get("auto_sos_minutes_after_overdue", {})
    return int(table.get(boat_type, max(table.values(), default=120)))


def auto_sos_at(planned_return: datetime, grace_minutes: int, boat_type: str) -> datetime:
    return planned_return + timedelta(minutes=grace_minutes + auto_sos_minutes(boat_type))


def went_offshore(max_offshore_km: Optional[float], has_track: bool) -> bool:
    """A boat with no position reports at all counts as offshore: unknown is never safe."""
    if not has_track:
        return True
    return (max_offshore_km or 0.0) >= float(_cfg().get("offshore_km", 2.0))


def phone_silent(last_ping_at: Optional[datetime], now: datetime) -> bool:
    if last_ping_at is None:
        return True
    return now - last_ping_at >= timedelta(minutes=int(_cfg().get("signal_silent_minutes", 60)))


def auto_sos_due(
    *,
    now: datetime,
    planned_return: datetime,
    grace_minutes: int,
    boat_type: str,
    max_offshore_km: Optional[float],
    has_track: bool,
    last_ping_at: Optional[datetime],
    last_offshore_km: Optional[float],
) -> bool:
    """True when the automatic SOS should go out now (the caller sends it once per round).

    Suppressed when the phone is still reporting from near the coast: a phone pinging from
    the harbour belongs to a fisher who is back and forgot to tap "I'm back".
    """
    if now < auto_sos_at(planned_return, grace_minutes, boat_type):
        return False
    if not went_offshore(max_offshore_km, has_track):
        return False
    offshore_now = (last_offshore_km or 0.0) >= float(_cfg().get("offshore_km", 2.0))
    return phone_silent(last_ping_at, now) or offshore_now


def timeline(planned_return: datetime, grace_minutes: int, boat_type: str) -> dict:
    """Shown on the trip screen, so the fisher knows exactly when each step happens.

    The contacts step uses the delay for an unknown sea state in daylight away from home,
    as an estimate; the monitor recomputes it with the real sea state when the time comes.
    """
    ask = planned_return + timedelta(minutes=grace_minutes)
    delay = max(0, min(MAX_DELAY_MINUTES, int(contact_delay_minutes(boat_type, "unknown", False, False))))
    return {
        "ask_at": ask,
        "contacts_at": ask + timedelta(minutes=delay),
        "auto_sos_at": auto_sos_at(planned_return, grace_minutes, boat_type),
        "offshore_km": float(_cfg().get("offshore_km", 2.0)),
        "signal_silent_minutes": int(_cfg().get("signal_silent_minutes", 60)),
    }
