"""Retrieval for the voice assistant: the facts it may use, and nothing else.

Corpus, rebuilt per request (it is small, and always fresh):
- knowledge base: how Sea Safe works, generated from thresholds.json so the assistant can
  never quote an out-of-date timing (auto-SOS delays, wave limits, report expiry).
- this fisher's own records: profile, contacts (names only), active and past trips,
  scheduled trips, recent alerts. Only the asking fisher's rows are ever loaded.
- public local data: official warnings, nearby hazard reports, upcoming events, recent
  harbour chat. Anything another person wrote is marked untrusted so the prompt fences it.

Ranking is BM25 over word tokens with a small synonym table (fishers say "back" and
"return", "rescue" and "SOS"). Pinned documents (profile, active trip, scheduled trips,
pending proposal) are always included because nearly every question depends on them.

Never in the corpus: phone numbers, user tokens, API keys, other fishers' positions or trips.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlmodel import Session, select

from ..db import as_utc, utcnow
from ..models import Alert, ChatMessage, Contact, Report, ScheduledTrip, Trip, User
from ..templates import explanations as tx
from ..thresholds import BOAT_TYPES, THRESHOLDS
from . import community, escalation, forecast, social


@dataclass
class Doc:
    id: str
    title: str
    text: str
    trusted: bool = True
    pinned: bool = False


# ---- tokenising and BM25 --------------------------------------------------

_STOP = set("a an the is are am was were be to of in on at for and or but it this that i me my you your we can do does "
            "will what when where how which who with from by as if so not any some there here please tell about".split())
_SYNONYMS = {
    "back": ["return"], "return": ["back"], "come": ["return"],
    "sos": ["emergency", "rescue"], "emergency": ["sos", "rescue"], "rescue": ["sos", "emergency"], "help": ["sos"],
    "danger": ["unsafe"], "dangerous": ["unsafe"], "storm": ["unsafe", "warning"],
    "schedule": ["plan", "trip"], "plan": ["schedule", "trip"], "book": ["schedule"], "expedition": ["trip"],
    "family": ["contact"], "wife": ["contact"], "contacts": ["contact"],
    "signal": ["network", "offline"], "network": ["signal"], "late": ["overdue"], "overdue": ["late"],
    "wave": ["waves"], "waves": ["wave"], "wind": ["gust"], "event": ["meeting"], "meeting": ["event"],
    "chat": ["community", "message"], "community": ["chat", "event"],
}


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokens(text: str, expand: bool = False) -> list[str]:
    words = [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOP]
    out = [_stem(w) for w in words]
    if expand:
        for w in words:
            out.extend(_stem(s) for s in _SYNONYMS.get(w, []))
    return out


SYNONYM_WEIGHT = 0.5


class BM25:
    def __init__(self, docs: list[Doc], k1: float = 1.4, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.tfs = [Counter(tokens(d.title + " " + d.text)) for d in docs]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avg = (sum(self.lens) / len(self.lens)) if self.lens else 1.0
        df: Counter = Counter()
        for tf in self.tfs:
            df.update(tf.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        # Words the fisher said count fully; synonyms count half, and each term only once.
        said = tokens(query)
        weights = {t: 1.0 for t in said}
        for t in tokens(query, expand=True)[len(said):]:
            weights.setdefault(t, SYNONYM_WEIGHT)
        out = []
        for tf, length in zip(self.tfs, self.lens):
            s = 0.0
            for t, w in weights.items():
                f = tf.get(t)
                if f:
                    s += w * self.idf.get(t, 0.0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * length / self.avg))
            out.append(s)
        return out

    def search(self, query: str, k: int) -> list[Doc]:
        ranked = sorted(zip(self.scores(query), range(len(self.docs))), key=lambda x: -x[0])
        return [self.docs[i] for s, i in ranked[:k] if s > 0]


# ---- corpus ----------------------------------------------------------------

def _tz_for(user: User) -> timezone:
    return timezone(timedelta(seconds=forecast._guess_offset(user.home_lat, user.home_lon)))


def _when(dt: Optional[datetime], tz: timezone) -> str:
    if dt is None:
        return "unknown"
    local = as_utc(dt).astimezone(tz)
    return f"{local.strftime('%a %d %b')} {tx.fmt_time(local, 'en')}"


def knowledge_base() -> list[Doc]:
    esc = THRESHOLDS.get("escalation", {})
    sos_mins = esc.get("auto_sos_minutes_after_overdue", {})
    boats = {b: tx.BOAT_WORD["en"].get(b, b) for b in BOAT_TYPES}
    docs = [
        Doc("kb:sos", "SOS button",
            "Press and hold the red SOS button for 2 seconds. The phone opens an SMS to all your emergency contacts with "
            "your position, and the server also alerts them if it can be reached. SMS needs a phone signal. The message "
            "says whether the position is a live GPS fix, a last known position, or only the home harbour. After SOS you "
            "can call the Coast Guard on 1554 with one tap."),
        Doc("kb:coastguard", "Coast Guard emergency number",
            "In India the Coast Guard maritime emergency number is 1554. Call it for any emergency at sea: sinking, fire, "
            "engine failure far from shore, someone overboard, injury, or being lost."),
        Doc("kb:overdue", "What happens if you are late (overdue)",
            "When you start a trip you set a return time. 30 minutes after it (the grace time) Sea Safe asks you "
            "'Are you back?'. Tap 'I'm back' or 'More time'. If you do not answer, your emergency contacts get an SMS "
            "saying you have not returned, with your last known position and the sea state."),
        Doc("kb:auto_sos", "Automatic SOS if you lose signal at sea and are very late",
            "If you lose signal at sea and are long overdue, with your phone silent, Sea Safe sends an AUTOMATIC SOS to your "
            "contacts with your last known position and asks them to call the Coast Guard on 1554. It waits a long time "
            "first so a trip that simply runs late does not cause a false alarm: "
            + ", ".join(f"{sos_mins.get(b, 120)} minutes after you become overdue for a {boats[b]}" for b in BOAT_TYPES)
            + f". It only fires if the boat went more than {esc.get('offshore_km', 2)} km out, and the phone has sent no "
            f"position for {esc.get('signal_silent_minutes', 60)} minutes or is still reporting from far offshore. "
            "If your phone is reporting from near the harbour, no automatic SOS is sent. Tapping 'More time' before you "
            "lose signal moves every step later. Tap 'I'm back' when ashore and your contacts are told you are safe."),
        Doc("kb:more_time", "Running late or losing signal",
            "Set a realistic return time before you leave. If the trip will run long, tap 'More time' while you still "
            "have signal; each tap adds 30 minutes and tells your contacts you are OK if they were already alerted. "
            "Out of signal the app still shows the forecast saved when the trip started and rings the head-back alarm."),
        Doc("kb:head_back", "Head back now alarm",
            "During a trip, if the forecast for your boat turns UNSAFE within the next 2 hours, Sea Safe sends "
            "'Head back now' with the reason. With no signal, the phone warns from the forecast saved at the start."),
        Doc("kb:schedule", "Scheduling a fishing trip",
            "You can schedule a trip by voice: say the day, when you will leave and when you will be back, for example "
            "'schedule a trip tomorrow, leave at 5 AM, back by 11 AM'. Sea Safe checks those hours with the risk engine. "
            "UNSAFE hours cannot be scheduled. You then say yes to confirm. One hour before you leave you get a reminder "
            "with a fresh forecast. When you go, open the Trip tab and tap Start on the scheduled trip so it is watched."),
        Doc("kb:verdicts", "What SAFE, CAUTION and UNSAFE mean",
            "Sea Safe gives each hour SAFE, CAUTION or UNSAFE for your boat type from waves, wind, gusts, rain, "
            "thunderstorms, official warnings and confirmed fisher reports. Missing or old forecast data is never SAFE. "
            "This is advisory only; always follow official warnings from INCOIS, IMD and the Coast Guard."),
        Doc("kb:reports", "Hazard reports (Sea Watch)",
            "In Sea Watch you can report rough sea, storm, rough harbour mouth, strong current, debris, oil spill, a boat "
            "in trouble, or no fish. Reports expire after a few hours. Another fisher must confirm a report before it "
            "raises the risk, and reports can raise the risk to CAUTION at most."),
        Doc("kb:community", "Community chat and events",
            f"The Community tab has harbour chat with fishers whose home harbour is within {int(social.HARBOUR_RADIUS_KM)} km, "
            f"and local events within {int(social.EVENT_RADIUS_KM)} km such as meetings, safety training, festivals and "
            "beach clean-ups. You can create an event, say you are going, and chat in each event's own channel. Others "
            "only see your name, never your phone number. Flag abusive messages; three flags hide a message."),
        Doc("kb:safety_kit", "What to carry",
            "Wear a life jacket. Carry your phone charged in a waterproof pouch, drinking water, a torch, a whistle and "
            "a knife. Tell someone ashore where you are going and when you will be back, and start a trip in Sea Safe."),
    ]
    for b in BOAT_TYPES:
        t = THRESHOLDS[b]
        docs.append(Doc(
            f"kb:limits:{b}", f"Limits for a {boats[b]}",
            f"For a {boats[b]}: waves from {t['wave_caution']} m are CAUTION and from {t['wave_unsafe']} m UNSAFE; "
            f"wind from {t['wind_caution']} km/h is CAUTION and from {t['wind_unsafe']} km/h UNSAFE; gusts from "
            f"{t['gust_unsafe']} km/h are UNSAFE. Thunderstorms are UNSAFE for every boat.",
        ))
    return docs


def user_docs(session: Session, user: User, now: datetime) -> list[Doc]:
    tz = _tz_for(user)
    boat = tx.BOAT_WORD["en"].get(user.boat_type, user.boat_type)
    wait = escalation.auto_sos_minutes(user.boat_type)
    docs = [Doc("me:profile", "Your profile",
                f"Your name is {user.name}. Boat type: {boat}. Home harbour: {user.home_name or 'not named'}. "
                f"For your boat the steps after your return time are: 30 minutes grace, then you are asked "
                f"'Are you back?', then your contacts are alerted, and only {wait} minutes after the grace time ends "
                f"(so {tx.fmt_duration(30 + wait)} after your return time) an automatic SOS is sent, if you went out to "
                f"sea and your phone is silent.", pinned=True)]

    contacts = session.exec(select(Contact).where(Contact.user_id == user.id)).all()
    if contacts:
        names = "; ".join(f"{c.name}" + (f" ({c.relation})" if c.relation else "") for c in contacts)
        docs.append(Doc("me:contacts", "Your emergency contacts",
                        f"You have {len(contacts)} emergency contact(s): {names}. They get your SOS and overdue alerts."))
    else:
        docs.append(Doc("me:contacts", "Your emergency contacts",
                        "You have no emergency contacts saved. Add one in Profile so SOS and overdue alerts reach someone.",
                        pinned=True))

    trips = session.exec(select(Trip).where(Trip.user_id == user.id).order_by(Trip.id.desc()).limit(6)).all()  # type: ignore[union-attr]
    for trip in trips:
        steps = escalation.timeline(trip.planned_return, trip.grace_minutes, user.boat_type)
        if trip.status in ("active", "overdue", "emergency"):
            docs.append(Doc(
                f"me:trip:{trip.id}", "Your trip at sea now",
                f"Trip in progress, status {trip.status}. Started {_when(trip.started_at, tz)}. Planned return "
                f"{_when(trip.planned_return, tz)}. You will be asked 'Are you back?' at {_when(steps['ask_at'], tz)}. "
                f"Your contacts are alerted from {_when(steps['contacts_at'], tz)} if you do not answer. Automatic SOS "
                f"from {_when(steps['auto_sos_at'], tz)} if you are offshore with no signal. Furthest out so far: "
                f"{(trip.max_offshore_km or 0):.1f} km. Last position report {_when(trip.last_ping_at, tz)}.",
                pinned=True,
            ))
        else:
            docs.append(Doc(f"me:trip:{trip.id}", "A past trip of yours",
                            f"Trip from {_when(trip.started_at, tz)}, planned return {_when(trip.planned_return, tz)}, "
                            f"ended {_when(trip.ended_at, tz)}, status {trip.status}."))

    scheduled = session.exec(
        select(ScheduledTrip).where(ScheduledTrip.user_id == user.id, ScheduledTrip.status.in_(("proposed", "scheduled")),  # type: ignore[union-attr]
                                    ScheduledTrip.return_at > now)
    ).all()
    for st in scheduled:
        label = "PENDING_PROPOSAL waiting for the fisher to say yes" if st.status == "proposed" else "Scheduled trip"
        docs.append(Doc(f"me:schedule:{st.id}", label,
                        f"{label}: leave {_when(st.depart_at, tz)}, back by {_when(st.return_at, tz)}. Sea at planning "
                        f"time: {st.verdict}.", pinned=True))
    if not scheduled:
        docs.append(Doc("me:schedule:none", "Scheduled trips", "You have no scheduled trips and no pending proposal.", pinned=True))

    alerts = session.exec(
        select(Alert).where(Alert.user_id == user.id, Alert.created_at > now - timedelta(days=3)).order_by(Alert.id.desc()).limit(5)  # type: ignore[union-attr]
    ).all()
    for a in alerts:
        docs.append(Doc(f"me:alert:{a.id}", "A recent alert", f"{a.kind} alert sent {_when(a.created_at, tz)} via {a.channel}."))
    return docs


def public_docs(session: Session, user: User, now: datetime) -> list[Doc]:
    tz = _tz_for(user)
    docs: list[Doc] = []
    for w in community.active_warnings(session, user.home_lat, user.home_lon, include_upcoming_hours=72):
        docs.append(Doc(f"warning:{w.id}", "Official warning", f"{w.title}. {w.message} (source: {w.source}, until {_when(w.expires_at, tz)})"))
    for r, d in community.nearby_reports(session, user.home_lat, user.home_lon, 25)[:8]:
        word = tx.REPORT_WORD["en"].get(r.type, r.type)
        note = f' Note from the reporter: "{r.note}"' if r.note else ""
        docs.append(Doc(f"report:{r.id}", "Fisher hazard report",
                        f"{word} reported {d:.0f} km away at {_when(r.created_at, tz)}, {r.up} confirmed, {r.down} disputed.{note}",
                        trusted=not r.note))
    for ev, d in social.upcoming_events(session, user.home_lat, user.home_lon, now)[:8]:
        docs.append(Doc(f"event:{ev.id}", "Community event",
                        f"Event '{ev.title}' ({ev.kind}) at {ev.place_name or 'a place nearby'}, {d:.0f} km away, "
                        f"on {_when(ev.starts_at, tz)}. {ev.description}", trusted=False))
    recent = session.exec(
        select(ChatMessage).where(ChatMessage.channel == "harbour", ChatMessage.hidden == False,  # noqa: E712
                                  ChatMessage.created_at > now - timedelta(hours=24)).order_by(ChatMessage.id.desc()).limit(40)  # type: ignore[union-attr]
    ).all()
    names: dict[int, str] = {}
    chats = 0
    for m in recent:
        if chats >= 10:
            break
        if social.haversine_km(user.home_lat, user.home_lon, m.lat, m.lon) > social.HARBOUR_RADIUS_KM:
            continue
        if m.user_id not in names:
            u = session.get(User, m.user_id)
            names[m.user_id] = u.name if u else "a fisher"
        author = names[m.user_id]
        chats += 1
        docs.append(Doc(f"chat:{m.id}", "Harbour chat message", f"{author} wrote at {_when(m.created_at, tz)}: {m.text}", trusted=False))
    return docs


def retrieve(session: Session, user: User, query: str, k: int = 6, now: Optional[datetime] = None) -> list[Doc]:
    """Pinned docs about this fisher, then the k best matches from everything else."""
    now = now or utcnow()
    corpus = knowledge_base() + user_docs(session, user, now) + public_docs(session, user, now)
    pinned = [d for d in corpus if d.pinned]
    rest = [d for d in corpus if not d.pinned]
    hits = BM25(rest).search(query, k) if rest else []
    if not any(h.id.startswith("kb:") for h in hits):
        # Always give the model at least the general safety facts.
        hits.append(next(d for d in rest if d.id == "kb:sos"))
    return pinned + hits


MIN_ANSWER_SCORE = 2.5


def best_answer(session: Session, user: User, query: str, now: Optional[datetime] = None) -> list[Doc]:
    """For the no-model path: the trusted documents that answer the question (one, or two when
    the question spans two topics about equally). Only Sea Safe's own knowledge and the
    fisher's own records qualify, never text written by other people."""
    now = now or utcnow()
    docs = [d for d in knowledge_base() + user_docs(session, user, now) if d.trusted]
    ranked = sorted(zip(BM25(docs).scores(query), docs), key=lambda p: -p[0])
    if not ranked or ranked[0][0] < MIN_ANSWER_SCORE:
        return []
    out = [ranked[0][1]]
    if len(ranked) > 1 and ranked[1][0] >= 0.6 * ranked[0][0]:
        out.append(ranked[1][1])
    return out


def split_trust(docs: Iterable[Doc]) -> tuple[list[Doc], list[Doc]]:
    docs = list(docs)
    return [d for d in docs if d.trusted], [d for d in docs if not d.trusted]
