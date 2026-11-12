"""Send alerts and log every attempt in the Alert table.

Channels: Expo push for the fisher; Twilio SMS and/or Telegram for contacts.
With no keys configured, alerts are stored with channel="simulated" so the alert
feed and the dashboard still show them.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx
from sqlmodel import Session, select

from ..config import settings
from ..models import Alert, Contact, User

log = logging.getLogger("seasafe.notify")
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def _log(session: Session, *, user_id, trip_id, kind, channel, recipient, message, status) -> Alert:
    alert = Alert(user_id=user_id, trip_id=trip_id, kind=kind, channel=channel, recipient=recipient, message=message, status=status)
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


async def _expo_push(token: str, title: str, body: str, data: dict) -> bool:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            EXPO_PUSH_URL,
            json={"to": token, "title": title, "body": body, "sound": "default", "priority": "high", "data": data},
        )
        resp.raise_for_status()
        result = (resp.json() or {}).get("data") or {}
        return result.get("status", "ok") == "ok"


async def _twilio_sms(to: str, body: str) -> bool:
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_sid}/Messages.json"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            url, data={"To": to, "From": settings.twilio_from, "Body": body}, auth=(settings.twilio_sid, settings.twilio_token)
        )
        resp.raise_for_status()
        return True


async def _telegram(chat_id: str, body: str) -> bool:
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"chat_id": chat_id, "text": body})
        resp.raise_for_status()
        return True


def twilio_configured() -> bool:
    return bool(settings.twilio_sid and settings.twilio_token and settings.twilio_from)


async def send_to_fisher(session: Session, user: User, message: str, kind: str, trip_id: Optional[int] = None) -> list[Alert]:
    """Push to the fisher's phone, or a simulated alert when there is no push token."""
    recipient = f"{user.name} (fisher)"
    if user.expo_push_token:
        try:
            ok = await _expo_push(user.expo_push_token, "Sea Safe", message, {"kind": kind, "trip_id": trip_id})
            return [_log(session, user_id=user.id, trip_id=trip_id, kind=kind, channel="push", recipient=recipient,
                         message=message, status="sent" if ok else "failed")]
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("expo push failed: %s", exc)
            return [_log(session, user_id=user.id, trip_id=trip_id, kind=kind, channel="push", recipient=recipient,
                         message=message, status="failed")]
    return [_log(session, user_id=user.id, trip_id=trip_id, kind=kind, channel="simulated", recipient=recipient,
                 message=message, status="simulated")]


async def send_to_contact(
    session: Session, contact: Contact, message: str, kind: str, user_id: Optional[int] = None, trip_id: Optional[int] = None
) -> list[Alert]:
    """SMS and/or Telegram to one emergency contact; simulated when neither is configured."""
    alerts: list[Alert] = []
    label = f"{contact.name} ({contact.relation})" if contact.relation else contact.name

    if twilio_configured() and contact.phone:
        try:
            await _twilio_sms(contact.phone, message)
            status = "sent"
        except httpx.HTTPError as exc:
            log.warning("twilio sms failed: %s", exc)
            status = "failed"
        alerts.append(_log(session, user_id=user_id, trip_id=trip_id, kind=kind, channel="sms",
                           recipient=f"{label} {contact.phone}", message=message, status=status))

    if settings.telegram_bot_token and contact.telegram_chat_id:
        try:
            await _telegram(contact.telegram_chat_id, message)
            status = "sent"
        except httpx.HTTPError as exc:
            log.warning("telegram send failed: %s", exc)
            status = "failed"
        alerts.append(_log(session, user_id=user_id, trip_id=trip_id, kind=kind, channel="telegram",
                           recipient=f"{label} (Telegram)", message=message, status=status))

    if not alerts:
        alerts.append(_log(session, user_id=user_id, trip_id=trip_id, kind=kind, channel="simulated",
                           recipient=f"{label} {contact.phone}".strip(), message=message, status="simulated"))
    return alerts


async def send_to_contacts(session: Session, user: User, message: str, kind: str, trip_id: Optional[int] = None) -> list[Alert]:
    contacts = session.exec(select(Contact).where(Contact.user_id == user.id)).all()
    alerts: list[Alert] = []
    for c in contacts:
        alerts.extend(await send_to_contact(session, c, message, kind, user_id=user.id, trip_id=trip_id))
    if not contacts:
        alerts.append(_log(session, user_id=user.id, trip_id=trip_id, kind=kind, channel="simulated",
                           recipient="(no emergency contacts saved)", message=message, status="simulated"))
    return alerts


def alert_out(alert: Alert) -> dict:
    from ..db import iso_utc

    return {
        "id": alert.id, "user_id": alert.user_id, "trip_id": alert.trip_id, "kind": alert.kind, "channel": alert.channel,
        "recipient": alert.recipient, "message": alert.message, "created_at": iso_utc(alert.created_at), "status": alert.status,
    }


async def telegram_poll_loop() -> None:
    """Optional: `/start <user_token>` in the bot chat links that chat as a family contact.

    Lets a judge join as a contact live. Runs only when TELEGRAM_BOT_TOKEN is set.
    """
    from ..db import engine

    base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
    offset = 0
    while True:
        try:
            async with httpx.AsyncClient(timeout=40) as client:
                resp = await client.get(f"{base}/getUpdates", params={"timeout": 30, "offset": offset})
                resp.raise_for_status()
                for update in resp.json().get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message") or {}
                    text = (msg.get("text") or "").strip()
                    chat = msg.get("chat") or {}
                    if not text.startswith("/start") or "id" not in chat:
                        continue
                    parts = text.split(maxsplit=1)
                    reply = "Send /start <code> using the code shown in the fisher's Sea Safe profile."
                    if len(parts) == 2:
                        with Session(engine) as session:
                            user = session.exec(select(User).where(User.token == parts[1].strip())).first()
                            if user:
                                chat_id = str(chat["id"])
                                existing = session.exec(
                                    select(Contact).where(Contact.user_id == user.id, Contact.telegram_chat_id == chat_id)
                                ).first()
                                if not existing:
                                    name = chat.get("first_name") or chat.get("username") or "Telegram contact"
                                    session.add(Contact(user_id=user.id, name=name, relation="telegram", telegram_chat_id=chat_id))
                                    session.commit()
                                reply = f"You will now get Sea Safe alerts for {user.name}."
                    await client.post(f"{base}/sendMessage", json={"chat_id": chat["id"], "text": reply})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("telegram poll error: %s", exc)
            await asyncio.sleep(5)
