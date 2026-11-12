from datetime import datetime, timezone

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

_url = settings.database_url
if _url.startswith("postgres://"):  # some hosts still hand out the old scheme
    _url = _url.replace("postgres://", "postgresql://", 1)
_connect_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}
engine = create_engine(_url, connect_args=_connect_args)


def init_db() -> None:
    from . import models  # noqa: F401  (registers the tables)

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


def utcnow() -> datetime:
    """Naive UTC. Everything in the database is naive UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc(dt: datetime) -> datetime:
    """Make a datetime timezone-aware UTC (naive values are assumed to be UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_naive_utc(dt: datetime) -> datetime:
    return as_utc(dt).replace(tzinfo=None)


def iso_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return as_utc(dt).isoformat().replace("+00:00", "Z")
