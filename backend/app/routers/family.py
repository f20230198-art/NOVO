"""The family member's phone: link with a code, then read alerts about the fisher."""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..db import get_session
from ..models import Contact, FamilyDevice
from ..services import family
from ..services.ratelimit import Limiter, SlidingWindow

router = APIRouter(prefix="/family", tags=["family"])
# Guessing a 6-digit code must be impractical.
link_limiter = Limiter(SlidingWindow(10, 60), SlidingWindow(50, 3600))


class LinkIn(BaseModel):
    code: str = Field(min_length=6, max_length=12)
    expo_push_token: Optional[str] = None


class PushIn(BaseModel):
    expo_push_token: Optional[str] = None


def current_family(
    x_family_token: Optional[str] = Header(default=None), session: Session = Depends(get_session)
) -> tuple[FamilyDevice, Contact]:
    device = session.exec(select(FamilyDevice).where(FamilyDevice.token == x_family_token)).first() if x_family_token else None
    contact = session.get(Contact, device.contact_id) if device else None
    if device is None or contact is None:
        raise HTTPException(status_code=401, detail="This phone is not linked. Enter the code again.")
    return device, contact


@router.post("/link")
def link(body: LinkIn, session: Session = Depends(get_session), x_forwarded_for: Optional[str] = Header(default=None)):
    if link_limiter.check(f"link:{x_forwarded_for or 'local'}"):
        raise HTTPException(status_code=429, detail="Too many attempts. Wait a minute and try again.")
    contact = family.contact_by_code(session, body.code)
    if contact is None:
        raise HTTPException(status_code=404, detail="That code was not found. Check the code in the fisher's Profile.")
    device = family.link(session, contact, body.expo_push_token)
    return {"token": device.token, **family.fisher_status(session, contact)}


@router.get("/me")
def me(fam=Depends(current_family), session: Session = Depends(get_session)):
    _, contact = fam
    return family.fisher_status(session, contact)


@router.get("/messages")
def messages(after_id: int = Query(default=0, ge=0), fam=Depends(current_family), session: Session = Depends(get_session)):
    _, contact = fam
    return family.messages(session, contact, after_id)


@router.put("/push")
def set_push(body: PushIn, fam=Depends(current_family), session: Session = Depends(get_session)):
    device, _ = fam
    device.expo_push_token = body.expo_push_token or None
    session.add(device)
    session.commit()
    return {"ok": True}


@router.delete("/me")
def unlink(fam=Depends(current_family), session: Session = Depends(get_session)):
    device, _ = fam
    session.delete(device)
    session.commit()
    return {"ok": True}
