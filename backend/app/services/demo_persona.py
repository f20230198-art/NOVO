"""Demo persona: Shibu Lopez, an outboard fisher from Vizhinjam, Kerala, and his harbour.

Everything here is made up for the hackathon demo and labelled as such:
  * phone numbers are +91 90000 000xx (not real numbers),
  * the official warning's source says it is a demo sample,
  * the weather is the `kerala_week` scenario, so the app shows its demo banner.

`load()` is idempotent: it removes every row the persona world created before (matched by the
phone prefix and the warning source) and writes it again. The persona fishers' user rows are
kept and reset, so their tokens survive a reload and a phone that adopted Shibu stays Shibu.
`clear()` removes it all, users included.

Run against a live server (the scenario lives in the server process, so seeding must go through it):
    python -m app.services.demo_persona load            # uses ADMIN_KEY from .env
    python -m app.services.demo_persona load --language ml   # Shibu uses the app in Malayalam
    python -m app.services.demo_persona clear --url http://192.168.1.20:8001
"""
from __future__ import annotations

import json
import math
import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import NaiveDatetime
from sqlmodel import Field, Session, SQLModel, select

from ..db import utcnow
from ..models import (Alert, AssistantMessage, Buddy, ChatMessage, CommunityEvent, Contact, EventRsvp, FamilyDevice,
                      MessageFlag, Report, ScheduledTrip, Trip, User, Vote, Warning)
from . import community, demo_weather, forecast, social
from .family import new_link_code
from .risk_engine import haversine_km

PHONE_PREFIX = "+9190000000"  # +91 90000 000xx: obviously fake
WARNING_SOURCE = "Demo persona (sample warning, not official)"
IST = demo_weather.IST


class DemoTrackPoint(SQLModel, table=True):
    """GPS track of a demo trip (real trips only keep the last position). Demo data only."""
    id: Optional[int] = Field(default=None, primary_key=True)
    trip_id: int = Field(index=True)
    seq: int
    lat: float
    lon: float
    at: NaiveDatetime  # naive UTC, like every other table


HARBOUR = ("Vizhinjam", 8.378, 76.989)

LANGUAGES = ("en", "ml")

PERSONA = {
    "key": "shibu", "name": "Shibu Lopez", "phone": PHONE_PREFIX + "10", "boat_type": "motorised",
    "home": HARBOUR,
    "boat": {
        "en": "St. Antony II, 26 ft fibreglass vallam with a 9.9 hp outboard, 3 crew, hand-lines and gill nets",
        "ml": "സെന്റ് ആന്റണി II: 26 അടി ഫൈബർ വള്ളം, 9.9 എച്ച്പി ഔട്ട്‌ബോർഡ് എഞ്ചിൻ, 3 പേർ, ചൂണ്ടയും ഒഴുക്കുവലയും",
    },
    "contacts": [
        ("Mercy Lopez", PHONE_PREFIX + "11", "wife"),
        ("Jose Lopez", PHONE_PREFIX + "12", "brother"),
    ],
}

NEIGHBOURS = [
    # key, name, phone, boat, (harbour, lat, lon), app language. Most write in Malayalam, a few in English.
    ("mani", "Mani Perera", PHONE_PREFIX + "20", "motorised", HARBOUR, "ml"),
    ("sahayam", "Sahayam Fernandez", PHONE_PREFIX + "21", "non_motorised", ("Poovar", 8.318, 77.068), "ml"),
    ("lawrence", "Lawrence D'Cruz", PHONE_PREFIX + "22", "motorised", ("Poonthura", 8.445, 76.930), "en"),
    ("yesudas", "Yesudas Thomas", PHONE_PREFIX + "23", "non_motorised", ("Adimalathura", 8.338, 77.025), "ml"),
    ("rafeeq", "Rafeeq Ali", PHONE_PREFIX + "24", "mechanised", HARBOUR, "en"),
]

# The head-back alert on the trip that was cut short, in the persona's language.
HEAD_BACK_TEXT = {
    "en": "Sea Safe (demo): wind rising to 32 km/h from the west by 10:00. Head back now.",
    "ml": "Sea Safe (ഡെമോ): 10 മണിയോടെ പടിഞ്ഞാറൻ കാറ്റ് മണിക്കൂറിൽ 32 കി.മീ. ആയി ഉയരും. ഇപ്പോൾ തിരിച്ചുപോകുക.",
}

# Warnings have one title and one message for everyone nearby, so the sample warning carries both
# languages (as printed notices on this coast often do). The engine's reason text quotes the title.
WARNING_TITLE = "Rough sea warning (demo sample) / പ്രക്ഷുബ്ധ കടൽ മുന്നറിയിപ്പ് (ഡെമോ മാതൃക)"
WARNING_MESSAGE = (
    "DEMO SAMPLE, not an official warning. Squally winds of 45-55 km/h gusting to 65 km/h and rough seas "
    "of 2.5-3.5 m are likely off the south Kerala coast. Fishers are advised not to venture into the sea.\n\n"
    "ഡെമോ മാതൃക, ഔദ്യോഗിക മുന്നറിയിപ്പല്ല. തെക്കൻ കേരള തീരത്ത് മണിക്കൂറിൽ 45-55 കി.മീ. വേഗതയിൽ, "
    "ചിലപ്പോൾ 65 കി.മീ. വരെ, ശക്തമായ കാറ്റും 2.5-3.5 മീറ്റർ ഉയരത്തിൽ തിരമാലയും ഉണ്ടാകാൻ സാധ്യതയുണ്ട്. "
    "മത്സ്യത്തൊഴിലാളികൾ കടലിൽ പോകരുത്."
)
BUDDIES = [("shibu", "mani"), ("shibu", "lawrence"), ("mani", "rafeeq")]

# Past trips of the persona: (days ago, leave hh:mm IST, back hh:mm IST, bearing out, km out, cut short)
PAST_TRIPS = [
    (9, (4, 30), (11, 40), 252, 18.0, False),
    (6, (4, 15), (12, 10), 238, 22.0, False),
    (4, (4, 45), (8, 50), 245, 14.0, True),   # came back early: the afternoon wind got up
    (1, (4, 20), (11, 15), 258, 16.0, False),
]


# ---- helpers -----------------------------------------------------------------

def _persona_users(session: Session) -> list[User]:
    return list(session.exec(select(User).where(User.phone.startswith(PHONE_PREFIX))).all())  # type: ignore[union-attr]


def _ist_today_midnight_utc(now: datetime) -> datetime:
    local = now.replace(tzinfo=timezone.utc).astimezone(IST)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)


def _offset(lat: float, lon: float, bearing_deg: float, km: float) -> tuple[float, float]:
    b = math.radians(bearing_deg)
    dlat = km * math.cos(b) / 110.574
    dlon = km * math.sin(b) / (111.320 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def _keep_at_sea(lat: float, lon: float) -> tuple[float, float]:
    if not demo_weather.is_sea(lat, lon):
        lon = demo_weather.coast_lon(lat) - 0.01
    return round(lat, 5), round(lon, 5)


def make_track(start: datetime, end: datetime, bearing: float, km_out: float, seed: int,
               home: tuple[float, float] = HARBOUR[1:]) -> list[tuple[float, float, datetime]]:
    """Out to the fishing ground, work it for a few hours, run home. One point every 10 minutes."""
    rng = random.Random(seed)
    total = (end - start).total_seconds() / 60
    steps = max(6, int(total // 10))
    out_frac, back_frac = 0.25, 0.2
    ground = _offset(home[0], home[1], bearing, km_out)
    pts: list[tuple[float, float, datetime]] = []
    lat, lon = ground
    for i in range(steps + 1):
        f = i / steps
        at = start + timedelta(minutes=total * f)
        if i in (0, steps):  # leaves from and ends at the harbour
            pts.append((home[0], home[1], at))
            continue
        if f <= out_frac:  # running out
            p = _offset(home[0], home[1], bearing + rng.uniform(-3, 3), km_out * f / out_frac)
        elif f >= 1 - back_frac:  # running home
            p = _offset(home[0], home[1], bearing + rng.uniform(-3, 3), km_out * (1 - f) / back_frac)
        else:  # working the ground: a slow wander, mostly with the current to the NNW
            heading = rng.uniform(300, 360) if rng.random() < 0.6 else rng.uniform(0, 360)
            lat, lon = _offset(lat, lon, heading, rng.uniform(0.2, 0.9))
            if haversine_km(ground[0], ground[1], lat, lon) > 4:  # motor back onto the ground
                lat, lon = ground
            p = (lat, lon)
        pts.append((*_keep_at_sea(*p), at))
    return pts


# ---- clear -------------------------------------------------------------------

def _clear_rows(session: Session, ids: list[int]) -> int:
    """Delete everything the persona world owns except the user rows. Returns the row count."""
    n = 0

    def drop(rows) -> None:
        nonlocal n
        for row in rows:
            session.delete(row)
            n += 1

    if ids:
        trip_ids = [t.id for t in session.exec(select(Trip).where(Trip.user_id.in_(ids))).all()]  # type: ignore[union-attr]
        if trip_ids:
            drop(session.exec(select(DemoTrackPoint).where(DemoTrackPoint.trip_id.in_(trip_ids))).all())  # type: ignore[union-attr]
        contact_ids = [c.id for c in session.exec(select(Contact).where(Contact.user_id.in_(ids))).all()]  # type: ignore[union-attr]
        if contact_ids:
            drop(session.exec(select(FamilyDevice).where(FamilyDevice.contact_id.in_(contact_ids))).all())  # type: ignore[union-attr]
        report_ids = [r.id for r in session.exec(select(Report).where(Report.user_id.in_(ids))).all()]  # type: ignore[union-attr]
        drop(session.exec(select(Vote).where(Vote.user_id.in_(ids))).all())  # type: ignore[union-attr]
        if report_ids:
            drop(session.exec(select(Vote).where(Vote.report_id.in_(report_ids))).all())  # type: ignore[union-attr]
        event_ids = [e.id for e in session.exec(select(CommunityEvent).where(CommunityEvent.created_by.in_(ids))).all()]  # type: ignore[union-attr]
        if event_ids:
            drop(session.exec(select(EventRsvp).where(EventRsvp.event_id.in_(event_ids))).all())  # type: ignore[union-attr]
            drop(session.exec(select(ChatMessage).where(ChatMessage.channel.in_([f"event:{i}" for i in event_ids]))).all())  # type: ignore[union-attr]
        drop(session.exec(select(EventRsvp).where(EventRsvp.user_id.in_(ids))).all())  # type: ignore[union-attr]
        msg_ids = [m.id for m in session.exec(select(ChatMessage).where(ChatMessage.user_id.in_(ids))).all()]  # type: ignore[union-attr]
        if msg_ids:
            drop(session.exec(select(MessageFlag).where(MessageFlag.message_id.in_(msg_ids))).all())  # type: ignore[union-attr]
        drop(session.exec(select(MessageFlag).where(MessageFlag.user_id.in_(ids))).all())  # type: ignore[union-attr]
        drop(session.exec(select(Buddy).where(Buddy.user_id.in_(ids) | Buddy.buddy_id.in_(ids))).all())  # type: ignore[union-attr]
        for model in (Contact, Trip, Alert, Report, ScheduledTrip, AssistantMessage, ChatMessage, CommunityEvent):
            col = model.created_by if model is CommunityEvent else model.user_id  # type: ignore[attr-defined]
            drop(session.exec(select(model).where(col.in_(ids))).all())  # type: ignore[union-attr]
    drop(session.exec(select(Warning).where(Warning.source == WARNING_SOURCE)).all())
    session.commit()
    return n


def clear(session: Session) -> dict:
    """Remove the whole persona world, users included, and switch the weather back to real."""
    users = _persona_users(session)
    removed = _clear_rows(session, [u.id for u in users])
    for u in users:
        session.delete(u)
    session.commit()
    if forecast.get_scenario() == demo_weather.MODE:
        forecast.set_scenario("real")
    return {"removed_rows": removed, "removed_users": len(users), "scenario": forecast.get_scenario()}


# ---- load --------------------------------------------------------------------

def _upsert_user(session: Session, existing: dict[str, User], name: str, phone: str, boat: str,
                 home: tuple[str, float, float], language: str = "en") -> User:
    user = existing.get(phone)
    if user is None:
        user = User(token=secrets.token_urlsafe(24), name=name, phone=phone, home_lat=home[1], home_lon=home[2])
    user.name, user.language, user.boat_type = name, language, boat
    user.home_name, user.home_lat, user.home_lon = home[0], home[1], home[2]
    user.planned_day = user.planned_verdict = user.recheck_sent_for = None
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _chat(session: Session, user: User, channel: str, text: str, at: datetime) -> ChatMessage:
    msg = ChatMessage(channel=channel, user_id=user.id, text=social.clean_text(text), lat=user.home_lat, lon=user.home_lon,
                      created_at=at)
    session.add(msg)
    return msg


def load(session: Session, now: Optional[datetime] = None, language: str = "en") -> dict:
    """(Re)create the persona world and switch the weather to the `kerala_week` scenario.

    `language` is Shibu's app language ("en" or "ml"). The harbour's own posts are a mix of
    Malayalam and English either way, as they would be in Vizhinjam.
    """
    if language not in LANGUAGES:
        raise ValueError(f"language must be one of {', '.join(LANGUAGES)}")
    now = now or utcnow()
    forecast.set_scenario(demo_weather.MODE)
    anchor = forecast.get_scenario_set_at().replace(tzinfo=None)  # naive UTC, like the database

    existing = {u.phone: u for u in _persona_users(session)}
    _clear_rows(session, [u.id for u in existing.values()])

    p = PERSONA
    users: dict[str, User] = {"shibu": _upsert_user(session, existing, p["name"], p["phone"], p["boat_type"], p["home"],
                                                     language)}
    for key, name, phone, boat, home, lang in NEIGHBOURS:
        users[key] = _upsert_user(session, existing, name, phone, boat, home, lang)
    shibu = users["shibu"]

    for name, phone, relation in p["contacts"]:
        session.add(Contact(user_id=shibu.id, name=name, phone=phone, relation=relation, link_code=new_link_code(session)))
        session.commit()
    for key, user in users.items():
        if key != "shibu":
            session.add(Contact(user_id=user.id, name=f"{user.name.split()[0]}'s family",
                                phone=user.phone[:-2] + "9" + user.phone[-1], relation="family",
                                link_code=new_link_code(session)))
    for a, b in BUDDIES:
        session.add(Buddy(user_id=users[a].id, buddy_id=users[b].id))
        session.add(Buddy(user_id=users[b].id, buddy_id=users[a].id))
    session.commit()

    # Past trips with GPS tracks.
    midnight = _ist_today_midnight_utc(now)
    trip_ids = []
    for i, (days, (h1, m1), (h2, m2), bearing, km, short) in enumerate(PAST_TRIPS):
        start = midnight - timedelta(days=days) + timedelta(hours=h1, minutes=m1)
        end = midnight - timedelta(days=days) + timedelta(hours=h2, minutes=m2)
        planned = midnight - timedelta(days=days) + timedelta(hours=12)
        track = make_track(start, end, bearing, km, seed=100 + i)
        trip = Trip(user_id=shibu.id, status="returned", started_at=start, planned_return=planned, ended_at=end,
                    start_lat=HARBOUR[1], start_lon=HARBOUR[2], last_lat=HARBOUR[1], last_lon=HARBOUR[2], last_ping_at=end,
                    forecast_snapshot="[]",
                    max_offshore_km=round(max(haversine_km(HARBOUR[1], HARBOUR[2], la, lo) for la, lo, _ in track), 1))
        session.add(trip)
        session.commit()
        session.refresh(trip)
        trip_ids.append(trip.id)
        for seq, (la, lo, at) in enumerate(track):
            session.add(DemoTrackPoint(trip_id=trip.id, seq=seq, lat=la, lon=lo, at=at))
        if short:
            session.add(Alert(user_id=shibu.id, trip_id=trip.id, kind="head_back", channel="simulated", recipient=shibu.name,
                              created_at=start + timedelta(hours=3, minutes=20),
                              message=HEAD_BACK_TEXT[language]))
        session.commit()

    # Mani is out right now, due back in about 4 hours (position private: buddies see "active" only).
    mani = users["mani"]
    mani_start = now - timedelta(hours=2, minutes=30)
    mani_track = make_track(mani_start, now + timedelta(hours=4), 242, 15.0, seed=7)
    so_far = [pt for pt in mani_track if pt[2] <= now]
    last = so_far[-1]
    session.add(Trip(user_id=mani.id, status="active", started_at=mani_start, planned_return=now + timedelta(hours=4),
                     start_lat=HARBOUR[1], start_lon=HARBOUR[2], last_lat=last[0], last_lon=last[1],
                     last_ping_at=now - timedelta(minutes=12), forecast_snapshot=json.dumps([]),
                     max_offshore_km=round(max(haversine_km(HARBOUR[1], HARBOUR[2], la, lo) for la, lo, _ in so_far), 1)))
    session.commit()

    # Hazard reports. Rule 2: only confirmed ones (voted up by another fisher) raise the risk,
    # and only to CAUTION. The two confirmed ones are just outside the 10 km report radius of
    # Vizhinjam, so Shibu's day starts clean; the harbour-mouth one is unconfirmed and inside,
    # so confirming it on stage (thumbs up) moves his verdict to CAUTION.
    R = community.create_report
    reports = {
        "mouth": R(session, "harbour_mouth_rough", 8.3745, 76.9886,
                   "രാവിലെ വേലിയിറക്ക സമയത്ത് അഴിമുഖത്ത് തിര പൊട്ടുന്നു. പുലിമുട്ടിന്റെ വശം ചേർന്ന് പോകുക.",
                   False, mani.id, now=now - timedelta(minutes=50)),
        "current": R(session, "strong_current", 8.280, 77.050,
                     "പൂവാറിന് പുറത്ത് വടക്കോട്ട് ശക്തമായ ഒഴുക്ക്, കട്ടമരങ്ങൾ വേഗം ഒഴുകിപ്പോകുന്നു.",
                     False, users["sahayam"].id, now=now - timedelta(hours=2)),
        "net": R(session, "debris", 8.470, 76.895,
                 "Ghost net floating about 12 km off Valiyathura, big one. Keep the outboard clear.",
                 False, users["lawrence"].id, now=now - timedelta(hours=3)),
        "far": R(session, "rough_sea", 8.665, 76.735, "Short steep waves outside Muthalapozhi bar.",
                 False, users["lawrence"].id, now=now - timedelta(hours=1)),
        "fish": R(session, "no_fish", 8.33, 76.94, "തെക്കേ പാരിൽ ഇന്ന് ചൂണ്ടയിൽ ഒന്നും കിട്ടിയില്ല.",
                  False, users["yesudas"].id, now=now - timedelta(hours=4)),
    }
    community.vote(session, reports["current"].id, users["yesudas"].id, "up")
    community.vote(session, reports["net"].id, mani.id, "up")
    community.vote(session, reports["net"].id, users["rafeeq"].id, "up")

    # A sample warning for the rough spell (official-looking, clearly marked as a demo sample).
    warn_start, warn_end = anchor + timedelta(hours=28), anchor + timedelta(hours=62)
    warning = Warning(
        title=WARNING_TITLE, message=WARNING_MESSAGE,
        center_lat=8.30, center_lon=76.85, radius_km=120, starts_at=warn_start, expires_at=warn_end, source=WARNING_SOURCE,
    )
    session.add(warning)
    session.commit()
    session.refresh(warning)

    # Harbour chat, back-dated through the day.
    for key, text, ago in [
        ("shibu", "ഇന്നലെ 11 മണിക്ക് തിരിച്ചെത്തി. 18 കിലോമീറ്റർ ഭാഗത്ത് നല്ല അയല കിട്ടി." if language == "ml"
         else "Back at 11 yesterday. Good mackerel on the 18 km ground.", timedelta(hours=20)),
        ("mani", "രാവിലെ 4:30-ന് ഇറങ്ങി. 15 കിലോമീറ്റർ വരെ കടൽ ശാന്തം. പാറയുടെ അടുത്ത് മത്തി ഉണ്ട്.",
         timedelta(hours=2, minutes=20)),
        ("lawrence", "Ghost net off Valiyathura, marked it in the app. Keep clear with the outboard.", timedelta(hours=2, minutes=55)),
        ("sahayam", "പൂവാർ ഭാഗത്ത് വടക്കോട്ട് ശക്തമായ ഒഴുക്ക്. കട്ടമരങ്ങൾ വേഗം ഒഴുകിപ്പോകുന്നു, സൂക്ഷിക്കണം.",
         timedelta(hours=1, minutes=55)),
        ("rafeeq", "Weather turning tomorrow evening. Our ring-seine boats stay in from tomorrow noon.", timedelta(hours=1)),
        ("yesudas", "ലൈഫ് ജാക്കറ്റ് പരിശോധനയ്ക്ക് ആരൊക്കെ വരുന്നുണ്ട്?", timedelta(minutes=40)),
        ("mani", "ഷിബു, നാളെ രാവിലെ നേരത്തെ ഇറങ്ങുന്നോ? ഒരുമിച്ച് പോയി 12 മണിക്ക് മുമ്പ് തിരിച്ചുവരാം.", timedelta(minutes=18)),
    ]:
        _chat(session, users[key], "harbour", text, now - ago)
    session.commit()

    # Community events near the harbour.
    events = [
        social.create_event(session, users["rafeeq"], title="മോശം കാലാവസ്ഥ: ഹാർബർ യോഗം", kind="meeting",
                            place_name="വിഴിഞ്ഞം ഹാർബർ ലേല ഹാൾ",
                            description="വള്ളങ്ങൾ എവിടെ കെട്ടണം, കടപ്പുറത്തെ കട്ടമരങ്ങൾ ആര് നോക്കും, ഈ ആഴ്ചത്തെ ബഡ്ഡി ബോട്ട് ലിസ്റ്റ്.",
                            lat=8.3785, lon=76.9878, starts_at=now + timedelta(hours=6)),
        social.create_event(session, users["lawrence"], title="Life-jacket and SOS check", kind="safety_drill",
                            place_name="Vizhinjam fish landing centre",
                            description="Bring your life jackets and phones. Volunteers check jackets, whistles and the SOS button.",
                            lat=8.3792, lon=76.9883, starts_at=now + timedelta(days=1, hours=1)),
        social.create_event(session, users["sahayam"], title="ഉപേക്ഷിച്ച വലകൾ നീക്കം ചെയ്യൽ", kind="cleanup",
                            place_name="വലിയതുറ കടൽപ്പാലം",
                            description="മോശം കാലാവസ്ഥയ്ക്ക് ശേഷം കടപ്പുറത്തും കടൽപ്പാലത്തിലും ഒഴുകിയെത്തിയ വലകൾ നീക്കാം.",
                            lat=8.4740, lon=76.9135, starts_at=now + timedelta(days=4, hours=2)),
    ]
    for key in ("shibu", "mani", "yesudas"):
        social.rsvp(session, events[1].id, users[key].id, True)
    for key in ("mani", "lawrence", "sahayam"):
        social.rsvp(session, events[0].id, users[key].id, True)
    _chat(session, users["lawrence"], f"event:{events[1].id}", "I'll bring spare whistles.", now - timedelta(minutes=30))
    session.commit()

    return {
        "persona": persona_out(session, shibu),
        "users": len(users),
        "past_trips": trip_ids,
        "reports": {k: r.id for k, r in reports.items()},
        "warning_id": warning.id,
        "events": [e.id for e in events],
        "scenario": forecast.get_scenario(),
        "rough_spell": {"starts": (anchor + timedelta(hours=demo_weather.BUILD_START)).isoformat() + "Z",
                        "peak": (anchor + timedelta(hours=demo_weather.PEAK_START)).isoformat() + "Z",
                        "ends": (anchor + timedelta(hours=demo_weather.EASE_END)).isoformat() + "Z"},
    }


# ---- read --------------------------------------------------------------------

def persona_user(session: Session) -> Optional[User]:
    return session.exec(select(User).where(User.phone == PERSONA["phone"])).first()


def persona_out(session: Session, user: User) -> dict:
    """What the phone needs to become Shibu: the profile (with its token) and the contacts."""
    contacts = session.exec(select(Contact).where(Contact.user_id == user.id)).all()
    return {
        "profile": {"name": user.name, "phone": user.phone, "language": user.language, "boat_type": user.boat_type,
                    "home_lat": user.home_lat, "home_lon": user.home_lon, "home_name": user.home_name,
                    "user_id": user.id, "token": user.token},
        "contacts": [{"id": c.id, "name": c.name, "phone": c.phone, "relation": c.relation, "link_code": c.link_code}
                     for c in contacts],
        "boat": PERSONA["boat"].get(user.language, PERSONA["boat"]["en"]),
        "demo": True,
    }


def trips_with_tracks(session: Session, user: User) -> list[dict]:
    from ..db import iso_utc

    trips = session.exec(select(Trip).where(Trip.user_id == user.id).order_by(Trip.started_at.desc())).all()  # type: ignore[union-attr]
    out = []
    for t in trips:
        pts = session.exec(select(DemoTrackPoint).where(DemoTrackPoint.trip_id == t.id).order_by(DemoTrackPoint.seq)).all()  # type: ignore[arg-type]
        out.append({
            "id": t.id, "status": t.status, "started_at": iso_utc(t.started_at), "ended_at": iso_utc(t.ended_at),
            "max_offshore_km": t.max_offshore_km,
            "track": [{"lat": p.lat, "lon": p.lon, "at": iso_utc(p.at)} for p in pts],
        })
    return out


# ---- command line --------------------------------------------------------------

def _main() -> None:
    import argparse

    import httpx

    from ..config import settings

    ap = argparse.ArgumentParser(description="Load or clear the Sea Safe demo persona on a running backend.")
    ap.add_argument("action", choices=["load", "clear"])
    ap.add_argument("--url", default="http://localhost:8001")
    ap.add_argument("--admin-key", default=settings.admin_key)
    ap.add_argument("--language", choices=LANGUAGES, default="en", help="Shibu's app language (load only)")
    args = ap.parse_args()
    method = "POST" if args.action == "load" else "DELETE"
    resp = httpx.request(method, args.url.rstrip("/") + "/demo/persona", headers={"X-Admin-Key": args.admin_key},
                         json={"language": args.language} if args.action == "load" else None, timeout=30)
    print(resp.status_code, json.dumps(resp.json(), indent=2))


if __name__ == "__main__":
    _main()
