"""Hazard reports (expiry, votes, nearby query) and official warnings."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from ..db import as_utc, iso_utc, utcnow
from ..models import Report, User, Warning
from .risk_engine import haversine_km

REPORT_EXPIRY_HOURS = {
    "rough_sea": 6,
    "storm": 6,
    "harbour_mouth_rough": 6,
    "strong_current": 6,
    "debris": 12,
    "oil_spill": 24,
    "boat_in_trouble": 3,
    "no_fish": 24,
}
HIDE_AT_NET_DOWN = 3  # a report with down - up >= 3 is hidden


def create_report(
    session: Session,
    type: str,
    lat: float,
    lon: float,
    note: Optional[str] = None,
    anonymous: bool = False,
    user_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Report:
    if type not in REPORT_EXPIRY_HOURS:
        raise ValueError(f"unknown report type {type}")
    now = now or utcnow()
    report = Report(
        user_id=user_id, type=type, lat=lat, lon=lon, note=(note or None), anonymous=anonymous,
        created_at=now, expires_at=now + timedelta(hours=REPORT_EXPIRY_HOURS[type]),
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def is_visible(report: Report, now: Optional[datetime] = None) -> bool:
    now = now or utcnow()
    return report.expires_at > now and (report.down - report.up) < HIDE_AT_NET_DOWN


def nearby_reports(
    session: Session, lat: Optional[float], lon: Optional[float], radius_km: float = 25, now: Optional[datetime] = None
) -> list[tuple[Report, Optional[float]]]:
    """Visible reports with their distance, nearest first. No lat/lon -> all visible reports."""
    now = now or utcnow()
    rows = session.exec(select(Report).where(Report.expires_at > now)).all()
    out: list[tuple[Report, Optional[float]]] = []
    for r in rows:
        if not is_visible(r, now):
            continue
        if lat is None or lon is None:
            out.append((r, None))
            continue
        d = haversine_km(lat, lon, r.lat, r.lon)
        if d <= radius_km:
            out.append((r, d))
    out.sort(key=lambda x: (x[1] if x[1] is not None else 0, -x[0].created_at.timestamp()))
    return out


def vote(session: Session, report_id: int, direction: str) -> Optional[Report]:
    report = session.get(Report, report_id)
    if report is None:
        return None
    if direction == "up":
        report.up += 1
    elif direction == "down":
        report.down += 1
    else:
        raise ValueError("dir must be 'up' or 'down'")
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def report_out(session: Session, report: Report, distance_km: Optional[float] = None) -> dict:
    name = None
    if report.user_id and not report.anonymous:
        user = session.get(User, report.user_id)
        name = user.name if user else None
    total = (report.expires_at - report.created_at).total_seconds() or 1
    left = (report.expires_at - utcnow()).total_seconds()
    return {
        "id": report.id,
        "type": report.type,
        "lat": report.lat,
        "lon": report.lon,
        "note": report.note,
        "anonymous": report.anonymous,
        "reporter": name,
        "created_at": iso_utc(report.created_at),
        "expires_at": iso_utc(report.expires_at),
        "life_left": max(0.0, min(1.0, left / total)),  # 1 = fresh, 0 = about to expire
        "up": report.up,
        "down": report.down,
        "distance_km": round(distance_km, 1) if distance_km is not None else None,
    }


def report_for_engine(report: Report) -> dict:
    return {
        "type": report.type, "lat": report.lat, "lon": report.lon,
        "created_at": as_utc(report.created_at), "expires_at": as_utc(report.expires_at),
        "up": report.up, "down": report.down,
    }


def active_warnings(
    session: Session, lat: Optional[float] = None, lon: Optional[float] = None,
    now: Optional[datetime] = None, include_upcoming_hours: int = 0,
) -> list[Warning]:
    """Warnings not yet expired (optionally only those covering a point)."""
    now = now or utcnow()
    horizon = now + timedelta(hours=include_upcoming_hours)
    rows = session.exec(select(Warning).where(Warning.expires_at > now, Warning.starts_at <= horizon)).all()
    if lat is None or lon is None:
        return list(rows)
    return [w for w in rows if haversine_km(lat, lon, w.center_lat, w.center_lon) <= w.radius_km]


def warning_for_engine(w: Warning) -> dict:
    return {
        "title": w.title, "center_lat": w.center_lat, "center_lon": w.center_lon, "radius_km": w.radius_km,
        "starts_at": as_utc(w.starts_at), "expires_at": as_utc(w.expires_at),
    }


def warning_out(w: Warning) -> dict:
    return {
        "id": w.id, "title": w.title, "message": w.message, "center_lat": w.center_lat, "center_lon": w.center_lon,
        "radius_km": w.radius_km, "starts_at": iso_utc(w.starts_at), "expires_at": iso_utc(w.expires_at), "source": w.source,
    }
