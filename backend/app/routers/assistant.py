from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..deps import current_user, require_admin
from ..models import AssistantMessage, User
from ..services import advisor as advisor_service
from ..services import assistant, assistant_tools, llm
from ..services.forecast import ForecastUnavailable
from ..services.ratelimit import Limiter, SlidingWindow

router = APIRouter(prefix="/assistant", tags=["assistant"])

# Per fisher. Keeps one phone (or a stuck mic loop) from using up the shared key pool.
limiter = Limiter(
    SlidingWindow(settings.assistant_per_minute, 60),
    SlidingWindow(settings.assistant_per_day, 24 * 3600),
)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    language: Optional[str] = Field(default=None, max_length=5)  # the app's language; else the profile's


@router.post("/chat")
async def chat(body: ChatIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    # An emergency is never rate limited.
    wait = 0.0 if assistant.is_emergency(body.message) else limiter.check(f"user:{user.id}")
    if wait:
        seconds = int(wait) + 1
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(seconds)},
            content={
                "detail": f"You are asking very fast. Please wait {seconds} seconds and try again. "
                          "For an emergency, press the red SOS button.",
                "retry_after": seconds,
            },
        )
    try:
        return await assistant.chat(session, user, body.message, language=body.language)
    except ForecastUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Forecast unavailable: {exc}")


@router.get("/day-plan")
async def day_plan(day_index: int = Query(default=0, ge=0, le=assistant.FORECAST_DAYS - 1),
                   period: Optional[str] = Query(default=None),
                   language: Optional[str] = Query(default=None, max_length=5),
                   user: User = Depends(current_user), session: Session = Depends(get_session)):
    """The same hour-by-hour advice Meera speaks, for the trip screen: the engine's best window,
    hours to avoid, harbour mouth and the run home. No LLM; facts only. Shape: assistant_tools.day_plan."""
    try:
        ctx = await advisor_service.compute(session, user.home_lat, user.home_lon, user.boat_type, days=assistant.FORECAST_DAYS)
    except ForecastUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Forecast unavailable: {exc}")
    lang = assistant.lang_of(language or user.language)
    plan = assistant_tools.day_plan(ctx, day_index, period if period in assistant_tools.PERIODS else None, lang)
    return {**plan, "spoken": assistant_tools.plan_spoken(plan, lang)}


@router.get("/history")
def history(user: User = Depends(current_user), session: Session = Depends(get_session)):
    return assistant.history_out(session, user)


@router.delete("/history")
def clear_history(user: User = Depends(current_user), session: Session = Depends(get_session)):
    for row in session.exec(select(AssistantMessage).where(AssistantMessage.user_id == user.id)).all():
        session.delete(row)
    session.commit()
    return {"ok": True}


@router.get("/status", dependencies=[Depends(require_admin)])
def status():
    """Key-pool health for the dashboard: labels and cool-downs only, never the keys."""
    return {"keys": llm.pool().status(), "per_minute": settings.assistant_per_minute, "per_day": settings.assistant_per_day}
