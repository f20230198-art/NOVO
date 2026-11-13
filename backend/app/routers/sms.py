"""Ask by SMS: the verdict for a basic phone, or a smartphone with no mobile data.

A fisher texts a few words and gets the risk engine's answer back as one SMS:

    SAFE                      -> today, for the sender's saved boat and harbour
    TOMORROW                  -> tomorrow
    KOCHI MOTOR TOMORROW      -> any harbour and boat, no account needed

The reply is built from the same templates as the app (no LLM), so it always carries the
engine's verdict. `POST /sms/inbound` is the Twilio webhook (form-encoded, answers TwiML);
`POST /sms/ask` is the same thing in JSON for the dashboard simulator and the tests.
"""
from typing import Optional
from urllib.parse import parse_qs
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..db import get_session
from ..models import Alert, User
from ..services import advisor as advisor_service
from ..services.forecast import ForecastUnavailable
from ..templates import explanations as tx
from .buddies import find_user_by_phone

router = APIRouter(prefix="/sms", tags=["sms"])

HARBOURS = {
    "muthalapozhi": (8.635, 76.775, "Muthalapozhi"), "mtp": (8.635, 76.775, "Muthalapozhi"),
    "മുതലപ്പൊഴി": (8.635, 76.775, "Muthalapozhi"),
    "vizhinjam": (8.375, 76.985, "Vizhinjam"), "vzm": (8.375, 76.985, "Vizhinjam"), "വിഴിഞ്ഞം": (8.375, 76.985, "Vizhinjam"),
    "kochi": (9.965, 76.235, "Kochi"), "cochin": (9.965, 76.235, "Kochi"), "കൊച്ചി": (9.965, 76.235, "Kochi"),
    "fujairah": (25.13, 56.36, "Fujairah"), "fuj": (25.13, 56.36, "Fujairah"),
}
BOATS = {
    "small": "non_motorised", "canoe": "non_motorised", "vallam": "non_motorised", "catamaran": "non_motorised",
    "വള്ളം": "non_motorised",
    "motor": "motorised", "outboard": "motorised", "മോട്ടോർ": "motorised",
    "big": "mechanised", "trawler": "mechanised", "mech": "mechanised", "ബോട്ട്": "mechanised",
}
HELP = {
    "en": "Sea Safe: text HARBOUR BOAT DAY, for example: KOCHI MOTOR TOMORROW. Harbours: Muthalapozhi, Vizhinjam, Kochi, Fujairah. Boats: SMALL, MOTOR, BIG.",
    "ml": "Sea Safe: ഹാർബർ, വള്ളം, ദിവസം എന്ന് അയക്കുക. ഉദാ: KOCHI MOTOR TOMORROW. ഹാർബറുകൾ: Muthalapozhi, Vizhinjam, Kochi, Fujairah. വള്ളം: SMALL, MOTOR, BIG.",
}
BAR = {
    "en": {"CAUTION": " Harbour mouth: rough, cross with care.", "UNSAFE": " Harbour mouth: breaking waves, do not cross."},
    "ml": {"CAUTION": " പൊഴിമുഖം: തിര ശക്തം, ശ്രദ്ധിച്ച് കടക്കുക.", "UNSAFE": " പൊഴിമുഖം: തിര പൊട്ടുന്നു, കടക്കരുത്."},
}


class SmsIn(BaseModel):
    sender: str = Field(default="", max_length=32)
    body: str = Field(max_length=300)


def parse(body: str, user: Optional[User]) -> Optional[dict]:
    """{lat, lon, place, boat, day, lang} from the text, filling gaps from the sender's profile."""
    text = (body or "").strip()
    words = [w.strip(".,?!").lower() for w in text.split()]
    harbour = next((HARBOURS[w] for w in words if w in HARBOURS), None)
    boat = next((BOATS[w] for w in words if w in BOATS), None)
    lang = "ml" if any("ഀ" <= ch <= "ൿ" for ch in text) else (user.language if user else "en")
    if harbour is None and user is not None:
        harbour = (user.home_lat, user.home_lon, user.home_name)
    if harbour is None:
        return None
    return {
        "lat": harbour[0], "lon": harbour[1], "place": harbour[2],
        "boat": boat or (user.boat_type if user else "non_motorised"),
        "day": min(2, tx.detect_day(text)),
        "lang": tx.lang_of(lang),
    }


async def answer(session: Session, sender: str, body: str) -> str:
    user = find_user_by_phone(session, sender) if sender else None
    ask = parse(body, user)
    if ask is None:
        reply = HELP[tx.lang_of(user.language if user else "en")]
    else:
        lang = ask["lang"]
        try:
            ctx = await advisor_service.compute(session, ask["lat"], ask["lon"], ask["boat"], days=3)
            day = ctx["days"][ask["day"]]
            bar = advisor_service.harbour_mouth_out(ctx, lang)["days"][ask["day"]]["worst_level"]
            reply = (
                f"Sea Safe, {ask['place']}, {tx.BOAT_WORD[lang][ask['boat']]}. "
                f"{tx.DAY_WORD[lang][ask['day']]}: {tx.VERDICT_WORD[lang][day['verdict']]}. "
                f"{tx.short_answer(day, lang)}{BAR[lang].get(bar, '')} {tx.ADVISORY[lang]}"
            )
        except ForecastUnavailable:
            # Unknown is never SAFE.
            reply = f"Sea Safe: {tx.VERDICT_WORD[lang]['CAUTION']}. No forecast right now. {tx.ADVISORY[lang]}"
    session.add(Alert(user_id=user.id if user else None, kind="sms_reply", channel="sms" if sender else "simulated",
                      recipient=sender or "sms simulator", message=reply, status="sent" if sender else "simulated"))
    session.commit()
    return reply


@router.post("/ask")
async def sms_ask(body: SmsIn, session: Session = Depends(get_session)):
    return {"reply": await answer(session, body.sender, body.body)}


@router.post("/inbound", include_in_schema=False)
async def sms_inbound(request: Request, session: Session = Depends(get_session)):
    """Twilio webhook: `From` and `Body` arrive form-encoded; the reply goes back as TwiML."""
    form = parse_qs((await request.body()).decode("utf-8", "replace"))
    reply = await answer(session, (form.get("From") or [""])[0], (form.get("Body") or [""])[0])
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(reply)}</Message></Response>'
    return Response(content=xml, media_type="application/xml")
