"""Scheduled trips: listed, confirmed, cancelled and started from the app (or by voice)."""
from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..db import get_session, utcnow
from ..deps import current_user
from ..models import ScheduledTrip, User
from ..services import forecast
from ..services.assistant import scheduled_out
from .trips import begin_trip

router = APIRouter(prefix="/schedule", tags=["schedule"])


class StartIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


def _tz(user: User):
    return timezone(timedelta(seconds=forecast._guess_offset(user.home_lat, user.home_lon)))


def _own(session: Session, user: User, sid: int) -> ScheduledTrip:
    st = session.get(ScheduledTrip, sid)
    if st is None or st.user_id != user.id:
        raise HTTPException(status_code=404, detail="Scheduled trip not found")
    return st


@router.get("")
def list_scheduled(user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = session.exec(
        select(ScheduledTrip).where(ScheduledTrip.user_id == user.id, ScheduledTrip.status.in_(("proposed", "scheduled")),  # type: ignore[union-attr]
                                    ScheduledTrip.return_at > utcnow()).order_by(ScheduledTrip.depart_at)  # type: ignore[arg-type]
    ).all()
    return [scheduled_out(s, _tz(user)) for s in rows]


@router.post("/{sid}/confirm")
def confirm(sid: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    st = _own(session, user, sid)
    if st.status != "proposed":
        raise HTTPException(status_code=409, detail="Only a proposed trip can be confirmed")
    st.status = "scheduled"
    session.add(st)
    session.commit()
    return scheduled_out(st, _tz(user))


@router.post("/{sid}/cancel")
def cancel(sid: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    st = _own(session, user, sid)
    if st.status not in ("proposed", "scheduled"):
        raise HTTPException(status_code=409, detail="This trip is not scheduled")
    st.status = "cancelled"
    session.add(st)
    session.commit()
    return scheduled_out(st, _tz(user))


@router.post("/{sid}/start")
async def start(sid: int, body: StartIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Turn a scheduled trip into a watched trip, returning at the scheduled time."""
    st = _own(session, user, sid)
    if st.status not in ("proposed", "scheduled"):
        raise HTTPException(status_code=409, detail="This trip is not scheduled")
    trip = await begin_trip(user, session, st.return_at, body.lat, body.lon, scheduled_id=st.id)
    st.status = "started"
    session.add(st)
    session.commit()
    return trip
