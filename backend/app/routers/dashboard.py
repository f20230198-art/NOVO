import logging
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from ..db import get_session, iso_utc, utcnow
from ..deps import require_admin
from ..models import ChatMessage, CommunityEvent, Trip, User
from ..services import advisor as advisor_service
from ..services import escalation, social
from ..services.monitor import trip_position

router = APIRouter(tags=["dashboard"])
log = logging.getLogger("seasafe.dashboard")

DASHBOARD_FILE = Path(__file__).resolve().parents[3] / "dashboard" / "index.html"


@router.get("/dashboard", include_in_schema=False)
def dashboard_page():
    if not DASHBOARD_FILE.exists():
        raise HTTPException(status_code=404, detail="dashboard/index.html not found")
    return FileResponse(DASHBOARD_FILE, media_type="text/html")


@router.get("/dashboard/trips", dependencies=[Depends(require_admin)])
async def dashboard_trips(session: Session = Depends(get_session)):
    """Every boat currently out (active, overdue or emergency) with the sea level at its position.

    Admin key required: live positions and phone numbers are private, and a boat's
    position gives away its fishing ground.
    """
    trips = session.exec(select(Trip).where(Trip.status.in_(("active", "overdue", "emergency")))).all()  # type: ignore[union-attr]
    out = []
    for trip in trips:
        user = session.get(User, trip.user_id)
        if user is None:
            continue
        lat, lon = trip_position(trip)
        level, waves, wind = None, None, None
        try:
            ctx = await advisor_service.compute(session, trip.start_lat, trip.start_lon, user.boat_type, days=1)
            current = advisor_service.current_conditions(ctx)
            if current:
                level, waves, wind = current["level"], current["wave_height"], current["wind_speed"]
        except Exception as exc:
            log.warning("dashboard: no sea state for trip %s: %s", trip.id, exc)
        out.append(
            {
                "id": trip.id, "status": trip.status, "name": user.name, "phone": user.phone, "boat_type": user.boat_type,
                "home_name": user.home_name, "lat": lat, "lon": lon,
                "started_at": iso_utc(trip.started_at), "planned_return": iso_utc(trip.planned_return),
                "grace_minutes": trip.grace_minutes, "last_ping_at": iso_utc(trip.last_ping_at),
                "minutes_late": max(0, int((utcnow() - trip.planned_return).total_seconds() // 60)),
                "level": level, "wave_height": waves, "wind_speed": wind,
                "max_offshore_km": round(trip.max_offshore_km or 0.0, 1),
                "auto_sos_at": iso_utc(escalation.auto_sos_at(trip.planned_return, trip.grace_minutes, user.boat_type)),
            }
        )
    return out


@router.get("/dashboard/community", dependencies=[Depends(require_admin)])
def dashboard_community(session: Session = Depends(get_session)):
    """Recent chat (for moderation, including hidden messages) and upcoming events, everywhere."""
    rows = session.exec(select(ChatMessage).order_by(ChatMessage.id.desc()).limit(40)).all()  # type: ignore[union-attr]
    names: dict[int, str] = {}
    messages = [{**social.message_out(session, m, None, names), "hidden": m.hidden, "flags": m.flags} for m in rows]
    events = session.exec(
        select(CommunityEvent).where(CommunityEvent.starts_at > utcnow() - timedelta(hours=6), CommunityEvent.cancelled == False)  # noqa: E712
        .order_by(CommunityEvent.starts_at)  # type: ignore[arg-type]
    ).all()
    return {"messages": messages, "events": [social.event_out(session, e, None) for e in events]}
