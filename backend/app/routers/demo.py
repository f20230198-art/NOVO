"""Demo helpers: scenario switch, fast-forward, seed data, manual monitor tick.

Left open (no admin key) on purpose so the phone's hidden demo panel can call them.
Do not deploy these to a real service.
"""
import json
import secrets
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session, utcnow
from ..models import (Alert, AssistantMessage, ChatMessage, CommunityEvent, Contact, Report, ScheduledTrip, Trip, User,
                      Warning)
from ..services import community, escalation, forecast, monitor, social

def _demo_only() -> None:
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="Demo endpoints are switched off (DEMO_MODE=false)")


router = APIRouter(prefix="/demo", tags=["demo"], dependencies=[Depends(_demo_only)])

SEED_PHONE_PREFIX = "+91000000"
SEED_SOURCE = "Demo seed"
SPOTS = [
    # name, harbour, lat, lon, language, boat, phone
    ("Biju", "Muthalapozhi", 8.635, 76.775, "ml", "non_motorised", SEED_PHONE_PREFIX + "0001"),
    ("Selvan", "Vizhinjam", 8.375, 76.985, "ml", "motorised", SEED_PHONE_PREFIX + "0002"),
    ("Antony", "Kochi", 9.965, 76.235, "en", "mechanised", SEED_PHONE_PREFIX + "0003"),
    ("Rashid", "Fujairah", 25.13, 56.36, "en", "motorised", SEED_PHONE_PREFIX + "0004"),
]


class ScenarioIn(BaseModel):
    mode: Literal["real", "calm", "rough", "storm", "worsening"]


@router.post("/scenario")
def set_scenario(body: ScenarioIn):
    forecast.set_scenario(body.mode)
    return {"mode": forecast.get_scenario()}


@router.get("/scenario")
def get_scenario():
    return {"mode": forecast.get_scenario()}


@router.post("/trips/{trip_id}/fast-forward")
def fast_forward(trip_id: int, session: Session = Depends(get_session)):
    """Move planned_return into the past so the monitor marks the trip overdue on its next tick."""
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    trip.planned_return = utcnow() - timedelta(minutes=trip.grace_minutes + 1)
    if trip.status == "overdue":
        trip.status = "active"
    session.add(trip)
    session.commit()
    return {"ok": True, "trip_id": trip.id, "status": trip.status}


@router.post("/trips/{trip_id}/lose-signal")
def lose_signal(trip_id: int, session: Session = Depends(get_session)):
    """Act out the auto-SOS case: the boat went 8 km out, the phone went silent, and the trip
    is now past the automatic-SOS time. The next monitor tick sends the automatic SOS."""
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    user = session.get(User, trip.user_id)
    now = utcnow()
    minutes = trip.grace_minutes + escalation.auto_sos_minutes(user.boat_type if user else "non_motorised") + 1
    trip.planned_return = now - timedelta(minutes=minutes)
    trip.started_at = trip.planned_return - timedelta(hours=4)
    trip.last_lat, trip.last_lon = trip.start_lat - 0.05, trip.start_lon - 0.05  # about 7-8 km out
    trip.max_offshore_km = max(trip.max_offshore_km or 0.0, 7.5)
    trip.last_ping_at = trip.planned_return - timedelta(minutes=90)
    trip.status = "active"
    session.add(trip)
    session.commit()
    return {"ok": True, "trip_id": trip.id, "planned_return": str(trip.planned_return)}


@router.post("/tick")
async def tick():
    """Run one monitor pass now instead of waiting for the next interval."""
    return await monitor.tick()


def _clear_seed(session: Session) -> None:
    users = session.exec(select(User).where(User.phone.startswith(SEED_PHONE_PREFIX))).all()  # type: ignore[union-attr]
    ids = [u.id for u in users]
    for model in (Contact, Trip, Alert, Report, ScheduledTrip, AssistantMessage, ChatMessage):
        if ids:
            for row in session.exec(select(model).where(model.user_id.in_(ids))).all():  # type: ignore[union-attr]
                session.delete(row)
    if ids:
        for ev in session.exec(select(CommunityEvent).where(CommunityEvent.created_by.in_(ids))).all():  # type: ignore[union-attr]
            session.delete(ev)
    for w in session.exec(select(Warning).where(Warning.source == SEED_SOURCE)).all():
        session.delete(w)
    for u in users:
        session.delete(u)
    session.commit()


@router.post("/seed")
def seed(session: Session = Depends(get_session)):
    """4 fishers at the test spots, contacts, 3 hazard reports, 1 official warning, 2 active trips.

    Safe to call again: earlier seed rows are removed first.
    """
    _clear_seed(session)
    now = utcnow()
    users = []
    for name, harbour, lat, lon, lang, boat, phone in SPOTS:
        user = User(token=secrets.token_urlsafe(24), name=name, phone=phone, language=lang, boat_type=boat,
                    home_lat=lat, home_lon=lon, home_name=harbour)
        session.add(user)
        session.commit()
        session.refresh(user)
        session.add(Contact(user_id=user.id, name=f"{name}'s family", phone=phone[:-1] + "9", relation="family"))
        session.add(Contact(user_id=user.id, name=f"{harbour} co-op", phone=phone[:-1] + "8", relation="co-op"))
        users.append(user)
    session.commit()
    biju, selvan, antony, rashid = users

    # Reports. The one beside Muthalapozhi is a no-fish report, which never changes the risk,
    # so the demo fisher starts from a clean slate before the live harbour-mouth report.
    reports = [
        community.create_report(session, "no_fish", 8.60, 76.74, "Nothing off the south bank this morning", False, biju.id),
        community.create_report(session, "debris", 8.36, 76.97, "Floating net and ropes near the breakwater", False, selvan.id),
        community.create_report(session, "rough_sea", 9.98, 76.20, "Short steep waves outside the channel", True, antony.id),
    ]

    warning = Warning(
        title="Rough sea warning, Fujairah coast",
        message="Waves up to 2.5 m offshore. Small boats are advised to stay ashore.",
        center_lat=25.13, center_lon=56.36, radius_km=40, starts_at=now, expires_at=now + timedelta(hours=12),
        source=SEED_SOURCE,
    )
    session.add(warning)

    trips = [
        # Out for a few more hours.
        Trip(user_id=selvan.id, status="active", started_at=now - timedelta(hours=2), planned_return=now + timedelta(hours=3),
             start_lat=8.375, start_lon=76.985, last_lat=8.34, last_lon=76.93, last_ping_at=now - timedelta(minutes=10),
             forecast_snapshot=json.dumps([])),
        # About to go overdue: 30 min grace runs out in about two minutes.
        Trip(user_id=antony.id, status="active", started_at=now - timedelta(hours=5), planned_return=now - timedelta(minutes=28),
             start_lat=9.965, start_lon=76.235, last_lat=9.93, last_lon=76.14, last_ping_at=now - timedelta(minutes=50),
             forecast_snapshot=json.dumps([])),
    ]
    for t in trips:
        session.add(t)
    session.commit()

    social.create_event(
        session, biju, title="Monsoon safety meeting", kind="safety_drill", place_name="Muthalapozhi harbour shed",
        description="Coast Guard volunteers show life-jacket checks and how to use SOS. Tea provided.",
        lat=8.637, lon=76.776, starts_at=now + timedelta(days=2, hours=3),
    )
    social.post_message(session, selvan, "harbour", "Harbour mouth was choppy at 6, calmer now.")
    social.post_message(session, biju, "harbour", "Anyone going out tomorrow early? Planning 5 to 11.")

    return {
        "users": [{"id": u.id, "name": u.name, "token": u.token, "home_name": u.home_name, "boat_type": u.boat_type} for u in users],
        "reports": [r.id for r in reports],
        "warning_id": warning.id,
        "trips": [t.id for t in trips],
    }
