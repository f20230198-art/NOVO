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
    _add_missing_columns()


def _add_missing_columns() -> None:
    """create_all never alters an existing table. Add new columns to an old database file
    (each new column has a default, so existing rows stay valid)."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl_type = col.type.compile(dialect=engine.dialect)
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                clause = ""
                if isinstance(default, bool):
                    clause = f" DEFAULT {int(default) if _url.startswith('sqlite') else str(default).upper()}"
                elif isinstance(default, (int, float)):
                    clause = f" DEFAULT {default}"
                elif isinstance(default, str):
                    clause = " DEFAULT '" + default.replace("'", "''") + "'"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl_type}{clause}'))


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
