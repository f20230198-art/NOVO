from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..db import get_session
from ..deps import current_user
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
def create(body: ReportIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """A registered fisher posts a report. `anonymous` hides the name from others, not from the server."""
    if body.type not in community.REPORT_EXPIRY_HOURS:
        raise HTTPException(status_code=422, detail=f"type must be one of {', '.join(community.REPORT_EXPIRY_HOURS)}")
    if community.reports_in_last_hour(session, user.id) >= community.MAX_REPORTS_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many reports in the last hour. Try again later.")
    report = community.create_report(session, body.type, body.lat, body.lon, body.note, body.anonymous, user_id=user.id)
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
def vote(report_id: int, body: VoteIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """One vote per fisher per report, and not on your own report."""
    try:
        report = community.vote(session, report_id, user.id, body.dir)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    out = community.report_out(session, report)
    out["hidden"] = not community.is_visible(report)
    return out
