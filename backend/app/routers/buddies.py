"""Buddy boats: fishers who pair up so that the nearest boat hears first.

The Coast Guard can be hours away; another fisher is often a few kilometres off. When a
fisher goes overdue or sends an SOS, every buddy gets the alert with the last position.
A buddy's position is shared only while that buddy is overdue or in an emergency.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..db import get_session, iso_utc
from ..deps import current_user
from ..models import Buddy, Trip, User
from ..services import risk_engine
from ..services.monitor import trip_position

router = APIRouter(prefix="/buddies", tags=["buddies"])

OPEN_STATUSES = ("active", "overdue", "emergency")


class BuddyIn(BaseModel):
    phone: str = Field(min_length=4, max_length=24)


def phone_key(phone: str) -> str:
    """Last 10 digits, so +91 98470 00001 and 9847000001 are the same number."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return digits[-10:]


def find_user_by_phone(session: Session, phone: str) -> Optional[User]:
    key = phone_key(phone)
    if len(key) < 6:
        return None
    for user in session.exec(select(User).order_by(User.id.desc())).all():  # type: ignore[union-attr]  # newest account wins
        if phone_key(user.phone) == key:
            return user
    return None


def _open_trip(session: Session, user_id: int) -> Optional[Trip]:
    return session.exec(
        select(Trip).where(Trip.user_id == user_id, Trip.status.in_(OPEN_STATUSES)).order_by(Trip.id.desc())  # type: ignore[union-attr]
    ).first()


def buddy_ids(session: Session, user_id: int) -> list[int]:
    return [b.buddy_id for b in session.exec(select(Buddy).where(Buddy.user_id == user_id)).all()]


def _buddy_out(session: Session, me: User, other: User) -> dict:
    trip = _open_trip(session, other.id)
    status = trip.status if trip else "ashore"
    out = {
        "id": other.id, "name": other.name, "boat_type": other.boat_type, "home_name": other.home_name,
        "status": status,
        "planned_return": iso_utc(trip.planned_return) if trip else None,
        "last_ping_at": iso_utc(trip.last_ping_at) if trip else None,
        "lat": None, "lon": None, "distance_km": None,
    }
    # Position only when the buddy may need help: a fishing ground is private otherwise.
    if trip and status in ("overdue", "emergency"):
        lat, lon = trip_position(trip)
        out["lat"], out["lon"] = lat, lon
        mine = _open_trip(session, me.id)
        here = trip_position(mine) if mine else (me.home_lat, me.home_lon)
        out["distance_km"] = round(risk_engine.haversine_km(here[0], here[1], lat, lon), 1)
    return out


@router.get("")
def list_buddies(user: User = Depends(current_user), session: Session = Depends(get_session)):
    out = []
    for other_id in buddy_ids(session, user.id):
        other = session.get(User, other_id)
        if other is not None:
            out.append(_buddy_out(session, user, other))
    return out


@router.post("")
def add_buddy(body: BuddyIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """Pair with another fisher by phone number. The link works both ways."""
    other = find_user_by_phone(session, body.phone)
    if other is None:
        raise HTTPException(status_code=404, detail="No Sea Safe fisher has that phone number")
    if other.id == user.id:
        raise HTTPException(status_code=422, detail="That is your own number")
    for a, b in ((user.id, other.id), (other.id, user.id)):
        exists = session.exec(select(Buddy).where(Buddy.user_id == a, Buddy.buddy_id == b)).first()
        if exists is None:
            session.add(Buddy(user_id=a, buddy_id=b))
    session.commit()
    return _buddy_out(session, user, other)


@router.delete("/{buddy_id}")
def remove_buddy(buddy_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = session.exec(
        select(Buddy).where(
            ((Buddy.user_id == user.id) & (Buddy.buddy_id == buddy_id))
            | ((Buddy.user_id == buddy_id) & (Buddy.buddy_id == user.id))
        )
    ).all()
    for row in rows:
        session.delete(row)
    session.commit()
    return {"ok": True}
