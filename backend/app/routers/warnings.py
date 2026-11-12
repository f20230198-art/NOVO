from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..db import get_session, to_naive_utc, utcnow
from ..deps import require_admin
from ..models import Warning
from ..services import community

router = APIRouter(prefix="/warnings", tags=["warnings"])


class WarningIn(BaseModel):
    title: str
    message: str = ""
    center_lat: float = Field(ge=-90, le=90)
    center_lon: float = Field(ge=-180, le=180)
    radius_km: float = Field(default=50, gt=0, le=2000)
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    hours: float = Field(default=12, gt=0, le=240)  # used when expires_at is omitted
    source: str = "admin"


@router.post("", dependencies=[Depends(require_admin)])
def create(body: WarningIn, session: Session = Depends(get_session)):
    starts = to_naive_utc(body.starts_at) if body.starts_at else utcnow()
    expires = to_naive_utc(body.expires_at) if body.expires_at else starts + timedelta(hours=body.hours)
    warning = Warning(
        title=body.title, message=body.message, center_lat=body.center_lat, center_lon=body.center_lon,
        radius_km=body.radius_km, starts_at=starts, expires_at=expires, source=body.source,
    )
    session.add(warning)
    session.commit()
    session.refresh(warning)
    return community.warning_out(warning)


@router.get("/active")
def active(
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lon: Optional[float] = Query(default=None, ge=-180, le=180),
    session: Session = Depends(get_session),
):
    return [community.warning_out(w) for w in community.active_warnings(session, lat, lon)]


@router.delete("/{warning_id}", dependencies=[Depends(require_admin)])
def delete(warning_id: int, session: Session = Depends(get_session)):
    warning = session.get(Warning, warning_id)
    if warning is not None:
        session.delete(warning)
        session.commit()
    return {"ok": True}
