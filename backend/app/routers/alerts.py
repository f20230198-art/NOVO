from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from ..db import get_session
from ..deps import current_user, require_admin
from ..models import Alert, User
from ..services.notify import alert_out

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/recent", dependencies=[Depends(require_admin)])
def recent(limit: int = Query(default=50, ge=1, le=200), session: Session = Depends(get_session)):
    """Latest alerts across all users, including simulated ones. The dashboard feed.

    Admin key required: the messages carry names and map links.
    """
    rows = session.exec(select(Alert).order_by(Alert.id.desc()).limit(limit)).all()  # type: ignore[union-attr]
    return [alert_out(a) for a in rows]


@router.get("")
def for_user(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    """The signed-in fisher's own alerts. There is no way to ask for another user's."""
    rows = session.exec(select(Alert).where(Alert.user_id == user.id).order_by(Alert.id.desc()).limit(limit)).all()  # type: ignore[union-attr]
    return [alert_out(a) for a in rows]
