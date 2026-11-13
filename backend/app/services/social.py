"""Community platform: harbour chat, events with RSVPs and per-event chat, flagging.

Privacy: other people see a fisher's name only, never a phone number or exact position.
Events are placed where the organiser says (a public meeting place), not where anyone lives.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from ..db import iso_utc, utcnow
from ..models import ChatMessage, CommunityEvent, EventRsvp, MessageFlag, User
from . import guard
from .risk_engine import haversine_km

HARBOUR_RADIUS_KM = 50.0  # "harbour" chat shows messages from fishers whose home is this close
EVENT_RADIUS_KM = 100.0
HIDE_AT_FLAGS = 3
MAX_MESSAGE_CHARS = 500
EVENT_KINDS = ("meeting", "training", "festival", "cleanup", "market", "safety_drill", "other")


def clean_text(text: str, cap: int = MAX_MESSAGE_CHARS) -> str:
    return guard._clean(text, cap)


# ---- events ---------------------------------------------------------------

def create_event(session: Session, user: User, *, title: str, description: str, kind: str, place_name: str,
                 lat: float, lon: float, starts_at: datetime) -> CommunityEvent:
    ev = CommunityEvent(
        created_by=user.id, title=clean_text(title, 120), description=clean_text(description, 1000),
        kind=kind if kind in EVENT_KINDS else "other", place_name=clean_text(place_name, 120),
        lat=lat, lon=lon, starts_at=starts_at,
    )
    session.add(ev)
    session.commit()
    session.refresh(ev)
    session.add(EventRsvp(event_id=ev.id, user_id=user.id))  # the organiser is going
    session.commit()
    return ev


def upcoming_events(session: Session, lat: float, lon: float, now: Optional[datetime] = None,
                    radius_km: float = EVENT_RADIUS_KM) -> list[tuple[CommunityEvent, float]]:
    now = now or utcnow()
    rows = session.exec(
        select(CommunityEvent).where(CommunityEvent.starts_at > now - timedelta(hours=6), CommunityEvent.cancelled == False)  # noqa: E712
    ).all()
    out = [(e, haversine_km(lat, lon, e.lat, e.lon)) for e in rows]
    out = [(e, d) for e, d in out if d <= radius_km]
    out.sort(key=lambda x: x[0].starts_at)
    return out


def rsvp(session: Session, event_id: int, user_id: int, going: bool) -> None:
    existing = session.exec(select(EventRsvp).where(EventRsvp.event_id == event_id, EventRsvp.user_id == user_id)).first()
    if going and existing is None:
        session.add(EventRsvp(event_id=event_id, user_id=user_id))
    elif not going and existing is not None:
        session.delete(existing)
    session.commit()


def event_out(session: Session, ev: CommunityEvent, viewer_id: Optional[int], distance_km: Optional[float] = None) -> dict:
    rsvps = session.exec(select(EventRsvp).where(EventRsvp.event_id == ev.id)).all()
    organiser = session.get(User, ev.created_by)
    return {
        "id": ev.id, "title": ev.title, "description": ev.description, "kind": ev.kind, "place_name": ev.place_name,
        "lat": ev.lat, "lon": ev.lon, "starts_at": iso_utc(ev.starts_at), "cancelled": ev.cancelled,
        "organiser": organiser.name if organiser else None, "is_organiser": ev.created_by == viewer_id,
        "going_count": len(rsvps), "going": any(r.user_id == viewer_id for r in rsvps),
        "distance_km": round(distance_km, 1) if distance_km is not None else None,
        "channel": f"event:{ev.id}",
    }


# ---- chat -----------------------------------------------------------------

def post_message(session: Session, user: User, channel: str, text: str) -> ChatMessage:
    msg = ChatMessage(channel=channel, user_id=user.id, text=clean_text(text), lat=user.home_lat, lon=user.home_lon)
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return msg


def messages(session: Session, viewer: User, channel: str, after_id: int = 0, limit: int = 50) -> list[ChatMessage]:
    q = select(ChatMessage).where(ChatMessage.channel == channel, ChatMessage.hidden == False, ChatMessage.id > after_id)  # noqa: E712
    rows = session.exec(q.order_by(ChatMessage.id.desc()).limit(limit * 4 if channel == "harbour" else limit)).all()  # type: ignore[union-attr]
    if channel == "harbour":
        rows = [m for m in rows if haversine_km(viewer.home_lat, viewer.home_lon, m.lat, m.lon) <= HARBOUR_RADIUS_KM][:limit]
    return list(reversed(rows))


def flag(session: Session, message_id: int, user_id: int) -> Optional[ChatMessage]:
    msg = session.get(ChatMessage, message_id)
    if msg is None:
        return None
    if msg.user_id == user_id:
        raise PermissionError("You cannot flag your own message")
    if session.exec(select(MessageFlag).where(MessageFlag.message_id == message_id, MessageFlag.user_id == user_id)).first():
        return msg
    session.add(MessageFlag(message_id=message_id, user_id=user_id))
    msg.flags += 1
    msg.hidden = msg.flags >= HIDE_AT_FLAGS
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return msg


def message_out(session: Session, msg: ChatMessage, viewer_id: Optional[int], names: Optional[dict[int, str]] = None) -> dict:
    if names is not None and msg.user_id in names:
        name = names[msg.user_id]
    else:
        author = session.get(User, msg.user_id)
        name = author.name if author else "a fisher"
        if names is not None:
            names[msg.user_id] = name
    return {
        "id": msg.id, "channel": msg.channel, "text": msg.text, "author": name, "mine": msg.user_id == viewer_id,
        "created_at": iso_utc(msg.created_at),
    }
