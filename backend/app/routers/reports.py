from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..db import get_session
from ..deps import optional_user
from ..models import User
from ..services import community

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportIn(BaseModel):
    type: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    note: Optional[str] = Field(default=None, max_length=280)
    anonymous: bool = False


class VoteIn(BaseModel):
    dir: Literal["up", "down"]


@router.get("/types")
def report_types():
    return community.REPORT_EXPIRY_HOURS


@router.post("")
def create(body: ReportIn, user: Optional[User] = Depends(optional_user), session: Session = Depends(get_session)):
    if body.type not in community.REPORT_EXPIRY_HOURS:
        raise HTTPException(status_code=422, detail=f"type must be one of {', '.join(community.REPORT_EXPIRY_HOURS)}")
    report = community.create_report(
        session, body.type, body.lat, body.lon, body.note, body.anonymous, user_id=user.id if user else None
    )
    return community.report_out(session, report)


@router.get("")
def list_reports(
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lon: Optional[float] = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=25, gt=0, le=20000),
    session: Session = Depends(get_session),
):
    return [community.report_out(session, r, d) for r, d in community.nearby_reports(session, lat, lon, radius_km)]


@router.post("/{report_id}/vote")
def vote(report_id: int, body: VoteIn, session: Session = Depends(get_session)):
    report = community.vote(session, report_id, body.dir)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    out = community.report_out(session, report)
    out["hidden"] = not community.is_visible(report)
    return out
