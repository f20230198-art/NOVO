import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..db import as_utc, get_session, iso_utc, to_naive_utc, utcnow
from ..deps import current_user
from ..models import Alert, Trip, User
from ..services import advisor as advisor_service
from ..services import forecast, notify
from ..services.monitor import _maps_link, trip_position
from ..templates import explanations as tx

router = APIRouter(prefix="/trips", tags=["trips"])
log = logging.getLogger("seasafe.trips")

OPEN_STATUSES = ("active", "overdue", "emergency")


class StartIn(BaseModel):
    planned_return: datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    grace_minutes: int = Field(default=30, ge=0, le=240)


class PointIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


def trip_out(trip: Trip, session: Session) -> dict:
    head_back = session.exec(
        select(Alert).where(Alert.trip_id == trip.id, Alert.kind == "head_back").order_by(Alert.id.desc())  # type: ignore[union-attr]
    ).first()
    try:
        snapshot = json.loads(trip.forecast_snapshot or "[]")
    except ValueError:
        snapshot = []
    return {
        "id": trip.id, "user_id": trip.user_id, "status": trip.status,
        "started_at": iso_utc(trip.started_at), "planned_return": iso_utc(trip.planned_return),
        "grace_minutes": trip.grace_minutes, "start_lat": trip.start_lat, "start_lon": trip.start_lon,
        "last_lat": trip.last_lat, "last_lon": trip.last_lon, "last_ping_at": iso_utc(trip.last_ping_at),
        "ended_at": iso_utc(trip.ended_at), "forecast_snapshot": snapshot,
        # Shown on the trip screen even when push notifications are not available.
        "head_back": {"message": head_back.message, "created_at": iso_utc(head_back.created_at)}
        if head_back and not trip.head_back_armed else None,
    }


def _own_trip(trip_id: int, user: User, session: Session) -> Trip:
    trip = session.get(Trip, trip_id)
    if trip is None or trip.user_id != user.id:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


def _open_trip(user: User, session: Session) -> Optional[Trip]:
    return session.exec(
        select(Trip).where(Trip.user_id == user.id, Trip.status.in_(OPEN_STATUSES)).order_by(Trip.id.desc())  # type: ignore[union-attr]
    ).first()


@router.post("/start")
async def start_trip(body: StartIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    now = utcnow()
    planned = to_naive_utc(body.planned_return)
    if planned <= now:
        raise HTTPException(status_code=422, detail="planned_return must be in the future")

    previous = _open_trip(user, session)
    if previous is not None:  # one open trip per fisher
        previous.status = "returned"
        previous.ended_at = now
        session.add(previous)

    # Hourly risk for the trip window, saved so the phone can show it with no signal.
    snapshot: list = []
    try:
        ctx = await advisor_service.compute(session, body.lat, body.lon, user.boat_type, days=3)
        end = as_utc(planned) + timedelta(hours=2)
        for item in advisor_service.forecast_payload(ctx, user.language, session)["hourly"]:
            t = datetime.fromisoformat(item["time"])
            if t + timedelta(hours=1) > ctx["now"] and t <= end:
                snapshot.append(item)
    except Exception as exc:  # a trip can still start without a forecast
        log.warning("start_trip: no forecast snapshot: %s", exc)

    trip = Trip(
        user_id=user.id, status="active", started_at=now, planned_return=planned, grace_minutes=body.grace_minutes,
        start_lat=body.lat, start_lon=body.lon, last_lat=body.lat, last_lon=body.lon, last_ping_at=now,
        forecast_snapshot=json.dumps(snapshot),
    )
    session.add(trip)
    session.commit()
    session.refresh(trip)
    return trip_out(trip, session)


@router.get("/active")
def active_trip(user: User = Depends(current_user), session: Session = Depends(get_session)):
    trip = _open_trip(user, session)
    return {"trip": trip_out(trip, session) if trip else None}


async def _raise_sos(trip: Trip, user: User, lat: float, lon: float, session: Session) -> dict:
    now = utcnow()
    trip.status = "emergency"
    trip.last_lat, trip.last_lon, trip.last_ping_at = lat, lon, now
    session.add(trip)
    session.commit()
    tz = timezone(timedelta(seconds=forecast._guess_offset(lat, lon)))
    local = as_utc(now).astimezone(tz)
    message = tx.alert_text(
        "sos", user.language, name=user.name, boat=tx.BOAT_WORD[tx.lang_of(user.language)].get(user.boat_type, user.boat_type),
        link=_maps_link(lat, lon), time=tx.fmt_time(local, user.language),
    )
    alerts = await notify.send_to_contacts(session, user, message, "sos", trip_id=trip.id)
    session.refresh(trip)
    return {"trip": trip_out(trip, session), "alerts": [notify.alert_out(a) for a in alerts]}


@router.post("/sos")
async def sos_without_trip(body: PointIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """SOS when no trip was started: uses the open trip if there is one, else creates an emergency trip."""
    trip = _open_trip(user, session)
    if trip is None:
        now = utcnow()
        trip = Trip(user_id=user.id, status="emergency", started_at=now, planned_return=now,
                    start_lat=body.lat, start_lon=body.lon)
        session.add(trip)
        session.commit()
        session.refresh(trip)
    return await _raise_sos(trip, user, body.lat, body.lon, session)


@router.get("/{trip_id}")
def get_trip(trip_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return trip_out(_own_trip(trip_id, user, session), session)


@router.post("/{trip_id}/ping")
def ping(trip_id: int, body: PointIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    trip = _own_trip(trip_id, user, session)
    trip.last_lat, trip.last_lon, trip.last_ping_at = body.lat, body.lon, utcnow()
    session.add(trip)
    session.commit()
    session.refresh(trip)
    return trip_out(trip, session)


@router.post("/{trip_id}/end")
def end_trip(trip_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    trip = _own_trip(trip_id, user, session)
    trip.status = "returned"
    trip.ended_at = utcnow()
    session.add(trip)
    session.commit()
    session.refresh(trip)
    return trip_out(trip, session)


@router.post("/{trip_id}/sos")
async def sos(trip_id: int, body: PointIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    trip = _own_trip(trip_id, user, session)
    return await _raise_sos(trip, user, body.lat, body.lon, session)
