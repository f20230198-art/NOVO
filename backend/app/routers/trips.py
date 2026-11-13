import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..db import as_utc, get_session, iso_utc, to_naive_utc, utcnow
from ..deps import current_user
from ..models import Alert, Trip, User
from ..services import advisor as advisor_service
from ..services import escalation, forecast, notify, risk_engine
from ..services.monitor import _maps_link, contacts_alerted, trip_position
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


class SosIn(PointIn):
    # How good the position is. The message to the contacts says so, because a rescuer
    # must not mistake the home harbour for where the boat is.
    fix: Literal["gps", "last_known", "home"] = "gps"


class TrackPoint(PointIn):
    at: datetime


class TrackIn(BaseModel):
    points: list[TrackPoint] = Field(min_length=1, max_length=300)


class ExtendIn(BaseModel):
    minutes: int = Field(default=30, ge=15, le=240)


def _local_time_label(user: User, lat: float, lon: float, when: datetime) -> str:
    tz = timezone(timedelta(seconds=forecast._guess_offset(lat, lon)))
    return tx.fmt_time(as_utc(when).astimezone(tz), user.language)


def trip_out(trip: Trip, session: Session) -> dict:
    head_back = session.exec(
        select(Alert).where(Alert.trip_id == trip.id, Alert.kind == "head_back").order_by(Alert.id.desc())  # type: ignore[union-attr]
    ).first()
    try:
        snapshot = json.loads(trip.forecast_snapshot or "[]")
    except ValueError:
        snapshot = []
    owner = session.get(User, trip.user_id)
    steps = escalation.timeline(trip.planned_return, trip.grace_minutes, owner.boat_type if owner else "non_motorised")
    auto_sos_sent = session.exec(select(Alert).where(Alert.trip_id == trip.id, Alert.kind == "auto_sos")).first() is not None
    return {
        "id": trip.id, "user_id": trip.user_id, "status": trip.status,
        "started_at": iso_utc(trip.started_at), "planned_return": iso_utc(trip.planned_return),
        "grace_minutes": trip.grace_minutes, "start_lat": trip.start_lat, "start_lon": trip.start_lon,
        "last_lat": trip.last_lat, "last_lon": trip.last_lon, "last_ping_at": iso_utc(trip.last_ping_at),
        "ended_at": iso_utc(trip.ended_at), "forecast_snapshot": snapshot,
        # False while the fisher is still being asked "are you back?".
        "contacts_alerted": contacts_alerted(session, trip),
        # Shown on the trip screen even when push notifications are not available.
        "head_back": {"message": head_back.message, "created_at": iso_utc(head_back.created_at)}
        if head_back and not trip.head_back_armed else None,
        "max_offshore_km": round(trip.max_offshore_km or 0.0, 1),
        "auto_sos_sent": auto_sos_sent,
        # When each step happens if there is no word from the fisher.
        "escalation": {
            "ask_at": iso_utc(steps["ask_at"]),
            "contacts_at": iso_utc(steps["contacts_at"]),
            "auto_sos_at": iso_utc(steps["auto_sos_at"]),
            "offshore_km": steps["offshore_km"],
            "signal_silent_minutes": steps["signal_silent_minutes"],
        },
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
    return await begin_trip(user, session, to_naive_utc(body.planned_return), body.lat, body.lon, body.grace_minutes)


async def begin_trip(user: User, session: Session, planned: datetime, lat: float, lon: float,
                     grace_minutes: int = 30, scheduled_id: Optional[int] = None) -> dict:
    """Start a watched trip. Also used when a scheduled trip is started."""
    now = utcnow()
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
        ctx = await advisor_service.compute(session, lat, lon, user.boat_type, days=3)
        end = as_utc(planned) + timedelta(hours=2)
        for item in advisor_service.forecast_payload(ctx, user.language, session)["hourly"]:
            t = datetime.fromisoformat(item["time"])
            if t + timedelta(hours=1) > ctx["now"] and t <= end:
                snapshot.append(item)
    except Exception as exc:  # a trip can still start without a forecast
        log.warning("start_trip: no forecast snapshot: %s", exc)

    trip = Trip(
        user_id=user.id, status="active", started_at=now, planned_return=planned, grace_minutes=grace_minutes,
        start_lat=lat, start_lon=lon, last_lat=lat, last_lon=lon, last_ping_at=now,
        forecast_snapshot=json.dumps(snapshot), scheduled_id=scheduled_id,
    )
    session.add(trip)
    session.commit()
    session.refresh(trip)
    return trip_out(trip, session)


@router.get("/active")
def active_trip(user: User = Depends(current_user), session: Session = Depends(get_session)):
    trip = _open_trip(user, session)
    return {"trip": trip_out(trip, session) if trip else None}


async def _raise_sos(trip: Trip, user: User, lat: float, lon: float, session: Session, fix: str = "gps") -> dict:
    now = utcnow()
    trip.status = "emergency"
    if fix == "gps":  # only a real fix replaces the last position on record
        trip.last_lat, trip.last_lon, trip.last_ping_at = lat, lon, now
    session.add(trip)
    session.commit()
    tz = timezone(timedelta(seconds=forecast._guess_offset(lat, lon)))
    local = as_utc(now).astimezone(tz)
    key = {"gps": "sos", "last_known": "sos_last_known", "home": "sos_home"}[fix]
    message = tx.alert_text(
        key, user.language, name=user.name, boat=tx.BOAT_WORD[tx.lang_of(user.language)].get(user.boat_type, user.boat_type),
        link=_maps_link(lat, lon), time=tx.fmt_time(local, user.language),
    )
    alerts = await notify.send_to_contacts(session, user, message, "sos", trip_id=trip.id)
    alerts += await notify.send_to_buddies(session, user, "buddy_sos", trip_id=trip.id, link=_maps_link(lat, lon))
    session.refresh(trip)
    return {"trip": trip_out(trip, session), "alerts": [notify.alert_out(a) for a in alerts]}


@router.post("/sos")
async def sos_without_trip(body: SosIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """SOS when no trip was started: uses the open trip if there is one, else creates an emergency trip."""
    trip = _open_trip(user, session)
    if trip is None:
        now = utcnow()
        trip = Trip(user_id=user.id, status="emergency", started_at=now, planned_return=now,
                    start_lat=body.lat, start_lon=body.lon)
        session.add(trip)
        session.commit()
        session.refresh(trip)
    return await _raise_sos(trip, user, body.lat, body.lon, session, body.fix)


@router.get("/{trip_id}")
def get_trip(trip_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return trip_out(_own_trip(trip_id, user, session), session)


@router.post("/{trip_id}/ping")
def ping(trip_id: int, body: PointIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    trip = _own_trip(trip_id, user, session)
    trip.last_lat, trip.last_lon, trip.last_ping_at = body.lat, body.lon, utcnow()
    out = risk_engine.haversine_km(trip.start_lat, trip.start_lon, body.lat, body.lon)
    trip.max_offshore_km = max(trip.max_offshore_km or 0.0, out)
    session.add(trip)
    session.commit()
    session.refresh(trip)
    return trip_out(trip, session)


@router.post("/{trip_id}/track")
def upload_track(trip_id: int, body: TrackIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Positions the phone recorded while it had no signal, sent when signal returns.

    They update how far out the boat went. The latest one becomes the last position, and
    the upload itself counts as contact from the phone (it has signal now).
    """
    trip = _own_trip(trip_id, user, session)
    now = utcnow()
    points = sorted((p for p in body.points if to_naive_utc(p.at) <= now + timedelta(minutes=5)), key=lambda p: p.at)
    for p in points:
        trip.max_offshore_km = max(trip.max_offshore_km or 0.0,
                                   risk_engine.haversine_km(trip.start_lat, trip.start_lon, p.lat, p.lon))
    if points:
        trip.last_lat, trip.last_lon = points[-1].lat, points[-1].lon
    trip.last_ping_at = now
    session.add(trip)
    session.commit()
    session.refresh(trip)
    return trip_out(trip, session)


@router.post("/{trip_id}/end")
async def end_trip(trip_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    trip = _own_trip(trip_id, user, session)
    was_open = trip.status in OPEN_STATUSES
    worried = was_open and contacts_alerted(session, trip)
    now = utcnow()
    trip.status = "returned"
    trip.ended_at = now
    session.add(trip)
    session.commit()
    if worried:  # the family was told something was wrong: tell them it is over
        lat, lon = trip_position(trip)
        message = tx.alert_text("all_clear", user.language, name=user.name, time=_local_time_label(user, lat, lon, now))
        await notify.send_to_contacts(session, user, message, "all_clear", trip_id=trip.id)
    session.refresh(trip)
    return trip_out(trip, session)


@router.post("/{trip_id}/extend")
async def extend_trip(trip_id: int, body: ExtendIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """"More time": push the return time back. Answers the "are you back?" check."""
    trip = _own_trip(trip_id, user, session)
    if trip.status not in ("active", "overdue"):
        raise HTTPException(status_code=409, detail="Only a trip that is still out can be given more time")
    worried = contacts_alerted(session, trip)
    now = utcnow()
    trip.planned_return = max(now, trip.planned_return) + timedelta(minutes=body.minutes)
    trip.status = "active"
    session.add(trip)
    session.commit()
    if worried:
        lat, lon = trip_position(trip)
        message = tx.alert_text("extended", user.language, name=user.name,
                                time=_local_time_label(user, lat, lon, trip.planned_return))
        await notify.send_to_contacts(session, user, message, "extended", trip_id=trip.id)
    session.refresh(trip)
    return trip_out(trip, session)


@router.post("/{trip_id}/sos")
async def sos(trip_id: int, body: SosIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    trip = _own_trip(trip_id, user, session)
    return await _raise_sos(trip, user, body.lat, body.lon, session, body.fix)
