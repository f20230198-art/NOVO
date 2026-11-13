from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..config import settings
from ..db import get_session
from ..deps import current_user, require_admin
from ..models import AssistantMessage, User
from ..services import assistant, llm
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
        return await assistant.chat(session, user, body.message)
    except ForecastUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Forecast unavailable: {exc}")


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
