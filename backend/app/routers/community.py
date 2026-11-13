"""Community platform: harbour chat, events, RSVPs, per-event chat."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..config import settings
from ..db import get_session, to_naive_utc, utcnow
from ..deps import current_user, require_admin
from ..models import ChatMessage, CommunityEvent, User
from ..services import social
from ..services.ratelimit import Limiter, SlidingWindow

router = APIRouter(prefix="/community", tags=["community"])
post_limiter = Limiter(SlidingWindow(settings.community_per_minute, 60), SlidingWindow(200, 24 * 3600))
event_limiter = Limiter(SlidingWindow(5, 24 * 3600))


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=social.MAX_MESSAGE_CHARS)


class EventIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=1000)
    kind: str = "meeting"
    place_name: str = Field(default="", max_length=120)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    starts_at: datetime


class RsvpIn(BaseModel):
    going: bool = True


def _too_fast(wait: float) -> JSONResponse:
    seconds = int(wait) + 1
    return JSONResponse(status_code=429, headers={"Retry-After": str(seconds)},
                        content={"detail": f"Please wait {seconds} seconds before posting again.", "retry_after": seconds})


def _check_channel(session: Session, channel: str) -> None:
    if channel == "harbour":
        return
    if channel.startswith("event:") and channel[6:].isdigit():
        ev = session.get(CommunityEvent, int(channel[6:]))
        if ev is not None and not ev.cancelled:
            return
    raise HTTPException(status_code=404, detail="Unknown channel")


@router.get("/messages")
def list_messages(channel: str = "harbour", after_id: int = Query(default=0, ge=0),
                  user: User = Depends(current_user), session: Session = Depends(get_session)):
    _check_channel(session, channel)
    names: dict[int, str] = {}
    return [social.message_out(session, m, user.id, names) for m in social.messages(session, user, channel, after_id)]


@router.post("/messages")
def post_message(body: MessageIn, channel: str = "harbour", user: User = Depends(current_user),
                 session: Session = Depends(get_session)):
    _check_channel(session, channel)
    wait = post_limiter.check(f"user:{user.id}")
    if wait:
        return _too_fast(wait)
    text = social.clean_text(body.text)
    if not text:
        raise HTTPException(status_code=422, detail="Message is empty")
    return social.message_out(session, social.post_message(session, user, channel, text), user.id)


@router.post("/messages/{message_id}/flag")
def flag_message(message_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    try:
        msg = social.flag(session, message_id, user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"ok": True, "hidden": msg.hidden}


@router.delete("/messages/{message_id}", dependencies=[Depends(require_admin)])
def remove_message(message_id: int, session: Session = Depends(get_session)):
    msg = session.get(ChatMessage, message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.hidden = True
    session.add(msg)
    session.commit()
    return {"ok": True}


@router.get("/events")
def list_events(user: User = Depends(current_user), session: Session = Depends(get_session)):
    return [social.event_out(session, e, user.id, d) for e, d in social.upcoming_events(session, user.home_lat, user.home_lon)]


@router.post("/events")
def create_event(body: EventIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    starts = to_naive_utc(body.starts_at)
    if starts <= utcnow():
        raise HTTPException(status_code=422, detail="The event must start in the future")
    wait = event_limiter.check(f"user:{user.id}")
    if wait:
        return _too_fast(wait)
    ev = social.create_event(
        session, user, title=body.title, description=body.description, kind=body.kind, place_name=body.place_name,
        lat=body.lat if body.lat is not None else user.home_lat, lon=body.lon if body.lon is not None else user.home_lon,
        starts_at=starts,
    )
    return social.event_out(session, ev, user.id, 0.0)


@router.post("/events/{event_id}/rsvp")
def rsvp(event_id: int, body: RsvpIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    ev = session.get(CommunityEvent, event_id)
    if ev is None or ev.cancelled:
        raise HTTPException(status_code=404, detail="Event not found")
    social.rsvp(session, event_id, user.id, body.going)
    return social.event_out(session, ev, user.id)


@router.delete("/events/{event_id}")
def cancel_event(event_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    ev = session.get(CommunityEvent, event_id)
    if ev is None or ev.created_by != user.id:
        raise HTTPException(status_code=404, detail="Event not found")
    ev.cancelled = True
    session.add(ev)
    session.commit()
    return {"ok": True}
