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


class Alert(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    trip_id: Optional[int] = Field(default=None, index=True)
    kind: str  # overdue/head_back/sos/morning_recheck/broadcast
    channel: str  # push/sms/telegram/simulated
    recipient: str
    message: str
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    status: str = "sent"
