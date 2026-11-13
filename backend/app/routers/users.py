import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..db import get_session, iso_utc
from ..deps import current_user
from ..models import Contact, FamilyDevice, User
from ..services.family import ensure_codes, new_link_code
from ..thresholds import BOAT_TYPES

router = APIRouter(prefix="/users", tags=["users"])


class ContactIn(BaseModel):
    name: str
    phone: str = ""
    relation: str = ""
    telegram_chat_id: Optional[str] = None


class UserIn(BaseModel):
    name: str
    phone: str = ""
    language: str = "en"
    boat_type: str = "non_motorised"
    home_lat: float = Field(ge=-90, le=90)
    home_lon: float = Field(ge=-180, le=180)
    home_name: str = ""
    expo_push_token: Optional[str] = None
    contacts: list[ContactIn] = []


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    language: Optional[str] = None
    boat_type: Optional[str] = None
    home_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    home_lon: Optional[float] = Field(default=None, ge=-180, le=180)
    home_name: Optional[str] = None
    expo_push_token: Optional[str] = None


def _check_boat(boat_type: Optional[str]) -> None:
    if boat_type is not None and boat_type not in BOAT_TYPES:
        raise HTTPException(status_code=422, detail=f"boat_type must be one of {', '.join(BOAT_TYPES)}")


def user_out(user: User) -> dict:
    return {
        "id": user.id, "name": user.name, "phone": user.phone, "language": user.language, "boat_type": user.boat_type,
        "home_lat": user.home_lat, "home_lon": user.home_lon, "home_name": user.home_name,
        "has_push_token": bool(user.expo_push_token), "created_at": iso_utc(user.created_at),
    }


def contact_out(c: Contact, session: Optional[Session] = None) -> dict:
    linked = bool(session and session.exec(select(FamilyDevice).where(FamilyDevice.contact_id == c.id)).first())
    return {"id": c.id, "name": c.name, "phone": c.phone, "relation": c.relation, "telegram": bool(c.telegram_chat_id),
            "link_code": c.link_code, "family_app": linked}


@router.post("")
def register(body: UserIn, session: Session = Depends(get_session)):
    _check_boat(body.boat_type)
    user = User(token=secrets.token_urlsafe(24), **body.model_dump(exclude={"contacts"}))
    session.add(user)
    session.commit()
    session.refresh(user)
    for c in body.contacts:
        session.add(Contact(user_id=user.id, link_code=new_link_code(session), **c.model_dump()))
        session.commit()
    return {"user_id": user.id, "token": user.token, "user": user_out(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.put("/me")
def update_me(body: UserUpdate, user: User = Depends(current_user), session: Session = Depends(get_session)):
    _check_boat(body.boat_type)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(user, key, value)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user_out(user)


@router.get("/me/contacts")
def list_contacts(user: User = Depends(current_user), session: Session = Depends(get_session)):
    rows = session.exec(select(Contact).where(Contact.user_id == user.id)).all()
    ensure_codes(session, rows)
    return [contact_out(c, session) for c in rows]


@router.post("/me/contacts")
def add_contact(body: ContactIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    contact = Contact(user_id=user.id, link_code=new_link_code(session), **body.model_dump())
    session.add(contact)
    session.commit()
    session.refresh(contact)
    return contact_out(contact, session)


@router.delete("/me/contacts/{contact_id}")
def delete_contact(contact_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)):
    contact = session.get(Contact, contact_id)
    if contact is None or contact.user_id != user.id:
        raise HTTPException(status_code=404, detail="Contact not found")
    for device in session.exec(select(FamilyDevice).where(FamilyDevice.contact_id == contact.id)).all():
        session.delete(device)  # the family phone stops receiving alerts
    session.delete(contact)
    session.commit()
    return {"ok": True}
