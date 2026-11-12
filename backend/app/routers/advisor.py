from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..db import get_session
from ..deps import optional_user
from ..models import User
from ..services import advisor as advisor_service
from ..services.forecast import ForecastUnavailable
from ..thresholds import BOAT_TYPES

router = APIRouter(prefix="/advisor", tags=["advisor"])


class AskIn(BaseModel):
    question: str = Field(max_length=500)
    language: Optional[str] = None
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)
    boat_type: Optional[str] = None


def _resolve(user: Optional[User], lat, lon, boat_type, language):
    """Fill in the saved boat, home location and language when the request omits them."""
    if lat is None or lon is None:
        if user is None:
            raise HTTPException(status_code=422, detail="lat and lon are required when no X-User-Token is sent")
        lat, lon = user.home_lat, user.home_lon
    boat = boat_type or (user.boat_type if user else "non_motorised")
    if boat not in BOAT_TYPES:
        raise HTTPException(status_code=422, detail=f"boat_type must be one of {', '.join(BOAT_TYPES)}")
    lang = language or (user.language if user else "en")
    return lat, lon, boat, lang


@router.post("/ask")
async def ask(body: AskIn, user: Optional[User] = Depends(optional_user), session: Session = Depends(get_session)):
    lat, lon, boat, lang = _resolve(user, body.lat, body.lon, body.boat_type, body.language)
    try:
        result = await advisor_service.ask(session, body.question, lang, lat, lon, boat, user.home_name if user else "")
    except ForecastUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Forecast unavailable: {exc}")
    if user is not None:  # remembered for the 3 AM morning re-check
        user.planned_day = result["date"]
        user.planned_verdict = result["verdict"]
        user.recheck_sent_for = None
        session.add(user)
        session.commit()
    return result


@router.get("/forecast")
async def get_forecast(
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lon: Optional[float] = Query(default=None, ge=-180, le=180),
    boat_type: Optional[str] = None,
    days: int = Query(default=3, ge=1, le=7),
    language: Optional[str] = None,
    user: Optional[User] = Depends(optional_user),
    session: Session = Depends(get_session),
):
    """Hourly strip + day summaries, no LLM. Used by the home screen."""
    lat, lon, boat, lang = _resolve(user, lat, lon, boat_type, language)
    try:
        ctx = await advisor_service.compute(session, lat, lon, boat, days=days)
    except ForecastUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Forecast unavailable: {exc}")
    return advisor_service.forecast_payload(ctx, lang, session)
