from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..db import get_session
from ..deps import optional_user
from ..models import Alert, User
from ..services.notify import alert_out

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/recent")
def recent(limit: int = Query(default=50, ge=1, le=200), session: Session = Depends(get_session)):
    """Latest alerts across all users, including simulated ones. The dashboard feed."""
    rows = session.exec(select(Alert).order_by(Alert.id.desc()).limit(limit)).all()  # type: ignore[union-attr]
    return [alert_out(a) for a in rows]


@router.get("")
def for_user(
    user_id: Optional[int] = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: Optional[User] = Depends(optional_user),
    session: Session = Depends(get_session),
):
    uid = user_id if user_id is not None else (user.id if user else None)
    if uid is None:
        raise HTTPException(status_code=422, detail="user_id or X-User-Token is required")
    rows = session.exec(select(Alert).where(Alert.user_id == uid).order_by(Alert.id.desc()).limit(limit)).all()  # type: ignore[union-attr]
    return [alert_out(a) for a in rows]
