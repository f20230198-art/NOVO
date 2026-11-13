from pydantic import NaiveDatetime
from typing import Optional

from sqlmodel import Field, SQLModel

from .db import utcnow


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(index=True, unique=True)
    name: str
    phone: str
    language: str = "en"
    boat_type: str = "non_motorised"
    home_lat: float
    home_lon: float
    home_name: str = ""
    expo_push_token: Optional[str] = None
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    # Last day the fisher asked about, for the 3 AM morning re-check.
    planned_day: Optional[str] = None  # local date, YYYY-MM-DD
    planned_verdict: Optional[str] = None
    recheck_sent_for: Optional[str] = None


class Contact(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    name: str
    phone: str = ""
    relation: str = ""
    telegram_chat_id: Optional[str] = None


class Trip(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    status: str = Field(default="active", index=True)  # active/returned/overdue/emergency
    started_at: NaiveDatetime = Field(default_factory=utcnow)
    planned_return: NaiveDatetime
    grace_minutes: int = 30
    start_lat: float
    start_lon: float
    last_lat: Optional[float] = None
    last_lon: Optional[float] = None
    last_ping_at: Optional[NaiveDatetime] = None
    forecast_snapshot: str = "[]"  # JSON text
    ended_at: Optional[NaiveDatetime] = None
    head_back_armed: bool = True  # False after a head-back push; re-armed when risk drops
    # Furthest the phone has reported from the start point. Auto-SOS only applies to a boat
    # that went out to sea, not to a phone left in the harbour.
    max_offshore_km: float = 0.0
    scheduled_id: Optional[int] = None  # the ScheduledTrip this trip was started from


class Report(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = None
    type: str
    lat: float
    lon: float
    note: Optional[str] = None
    anonymous: bool = False
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    expires_at: NaiveDatetime
    up: int = 0
    down: int = 0


class Vote(SQLModel, table=True):
    """One vote per fisher per report, so a report cannot be buried or boosted by one person."""
    id: Optional[int] = Field(default=None, primary_key=True)
    report_id: int = Field(index=True)
    user_id: int = Field(index=True)
    dir: str  # up/down


class Warning(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    message: str = ""
    center_lat: float
    center_lon: float
    radius_km: float = 50
    starts_at: NaiveDatetime = Field(default_factory=utcnow)
    expires_at: NaiveDatetime
    source: str = "admin"


class ScheduledTrip(SQLModel, table=True):
    """A trip planned ahead, usually by voice. `proposed` until the fisher confirms it."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    status: str = Field(default="proposed", index=True)  # proposed/scheduled/started/cancelled/expired
    depart_at: NaiveDatetime
    return_at: NaiveDatetime
    verdict: str = "CAUTION"  # worst engine level over the planned hours when it was made
    note: str = ""
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    reminder_sent: bool = False


class AssistantMessage(SQLModel, table=True):
    """Voice-assistant conversation, so each stateless LLM call can be given recent history."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    role: str  # user/assistant
    text: str
    action: Optional[str] = None  # JSON of the action taken, for the assistant side
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class CommunityEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_by: int = Field(index=True)
    title: str
    description: str = ""
    kind: str = "meeting"  # meeting/training/festival/cleanup/market/other
    place_name: str = ""
    lat: float
    lon: float
    starts_at: NaiveDatetime
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    cancelled: bool = False


class EventRsvp(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(index=True)
    user_id: int = Field(index=True)


class ChatMessage(SQLModel, table=True):
    """Community chat. `channel` is "harbour" (fishers near the author's home) or "event:<id>"."""
    id: Optional[int] = Field(default=None, primary_key=True)
    channel: str = Field(index=True)
    user_id: int = Field(index=True)
    text: str
    # Author's home harbour when posted, so "harbour" chat can be filtered by distance.
    lat: float
    lon: float
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    flags: int = 0
    hidden: bool = False


class MessageFlag(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    message_id: int = Field(index=True)
    user_id: int = Field(index=True)


class Alert(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    trip_id: Optional[int] = Field(default=None, index=True)
    kind: str  # overdue_check/overdue/auto_sos/head_back/sos/morning_recheck/trip_reminder/all_clear/extended
    channel: str  # push/sms/telegram/simulated
    recipient: str
    message: str
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    status: str = "sent"
