import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from ..db import get_session, iso_utc, utcnow
from ..models import Trip, User
from ..services import advisor as advisor_service
from ..services.monitor import trip_position

router = APIRouter(tags=["dashboard"])
log = logging.getLogger("seasafe.dashboard")

DASHBOARD_FILE = Path(__file__).resolve().parents[3] / "dashboard" / "index.html"


@router.get("/dashboard", include_in_schema=False)
def dashboard_page():
    if not DASHBOARD_FILE.exists():
        raise HTTPException(status_code=404, detail="dashboard/index.html not found")
    return FileResponse(DASHBOARD_FILE, media_type="text/html")


@router.get("/dashboard/trips")
async def dashboard_trips(session: Session = Depends(get_session)):
    """Every boat currently out (active, overdue or emergency) with the sea level at its position."""
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
            }
        )
    return out
