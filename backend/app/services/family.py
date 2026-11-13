"""Family phones: an emergency contact links their own Sea Safe app with a 6-digit code and
then receives every alert sent to them, as a notification and in a message inbox."""
from __future__ import annotations

import secrets
from typing import Iterable, Optional

from sqlmodel import Session, select

from ..db import iso_utc
from ..models import Alert, Contact, FamilyDevice, Trip, User

# Alerts a family phone shows. Messages meant for the fisher never reach the family.
FAMILY_KINDS = ("overdue", "sos", "auto_sos", "all_clear", "extended")


def new_link_code(session: Session) -> str:
    for _ in range(50):
        code = f"{secrets.randbelow(900000) + 100000}"
        if session.exec(select(Contact).where(Contact.link_code == code)).first() is None:
            return code
    raise RuntimeError("could not find a free link code")


def ensure_codes(session: Session, contacts: Iterable[Contact]) -> None:
    changed = False
    for c in contacts:
        if not c.link_code:
            c.link_code = new_link_code(session)
            session.add(c)
            changed = True
    if changed:
        session.commit()


def contact_by_code(session: Session, code: str) -> Optional[Contact]:
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != 6:
        return None
    return session.exec(select(Contact).where(Contact.link_code == code)).first()


def link(session: Session, contact: Contact, push_token: Optional[str]) -> FamilyDevice:
    device = FamilyDevice(contact_id=contact.id, token=secrets.token_urlsafe(24), expo_push_token=push_token or None)
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


def fisher_status(session: Session, contact: Contact) -> dict:
    """What the family sees about the fisher: name, harbour, boat and the trip's state.
    The live position is not included; position links arrive inside the alert messages."""
    user = session.get(User, contact.user_id)
    trip = session.exec(
        select(Trip).where(Trip.user_id == contact.user_id).order_by(Trip.id.desc())  # type: ignore[union-attr]
    ).first()
    trip_out = None
    if trip is not None:
        trip_out = {
            "status": trip.status, "started_at": iso_utc(trip.started_at), "planned_return": iso_utc(trip.planned_return),
            "ended_at": iso_utc(trip.ended_at), "last_contact_at": iso_utc(trip.last_ping_at),
        }
    return {
        "contact": {"name": contact.name, "relation": contact.relation},
        "fisher": {"name": user.name if user else "", "home_name": user.home_name if user else "",
                   "boat_type": user.boat_type if user else ""},
        "trip": trip_out,
    }


def messages(session: Session, contact: Contact, after_id: int = 0, limit: int = 100) -> list[dict]:
    rows = session.exec(
        select(Alert).where(Alert.contact_id == contact.id, Alert.id > after_id, Alert.kind.in_(FAMILY_KINDS))  # type: ignore[union-attr]
        .order_by(Alert.id.desc()).limit(limit)  # type: ignore[union-attr]
    ).all()
    # One message per alert event: SMS, Telegram and app copies of it are logged back to back.
    out: list[dict] = []
    for a in reversed(rows):
        if out and out[-1]["kind"] == a.kind and out[-1]["text"] == a.message:
            continue
        out.append({"id": a.id, "kind": a.kind, "text": a.message, "created_at": iso_utc(a.created_at),
                    "urgent": a.kind in ("sos", "auto_sos", "overdue")})
    return out
