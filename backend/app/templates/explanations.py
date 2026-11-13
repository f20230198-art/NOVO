"""Deterministic explanation text in English and Malayalam.

Used when there is no ANTHROPIC_API_KEY, when the Claude call fails, and whenever the
model's answer disagrees with the risk engine. The Malayalam strings are a first draft
and must be reviewed by a native speaker (see backend/README.md).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

LANGS = ("en", "ml")

VERDICT_WORD = {
    "en": {"SAFE": "SAFE", "CAUTION": "CAUTION", "UNSAFE": "UNSAFE"},
    "ml": {"SAFE": "സുരക്ഷിതം", "CAUTION": "ജാഗ്രത", "UNSAFE": "അപകടം"},
}

ADVISORY = {
    "en": "Advisory only. Always follow official warnings (INCOIS / IMD / Coast Guard 1554).",
    "ml": "ഇത് ഉപദേശം മാത്രം. ഔദ്യോഗിക മുന്നറിയിപ്പുകൾ (INCOIS / IMD / കോസ്റ്റ് ഗാർഡ് 1554) എപ്പോഴും പാലിക്കുക.",
}

DAY_WORD = {
    "en": ["Today", "Tomorrow", "The day after tomorrow"],
    "ml": ["ഇന്ന്", "നാളെ", "മറ്റന്നാൾ"],
}

BOAT_WORD = {
    "en": {"non_motorised": "non-motorised boat", "motorised": "motor boat", "mechanised": "mechanised boat"},
    "ml": {"non_motorised": "യന്ത്രമില്ലാത്ത വള്ളം", "motorised": "മോട്ടോർ വള്ളം", "mechanised": "യന്ത്രവൽകൃത ബോട്ട്"},
}

REPORT_WORD = {
    "en": {
        "rough_sea": "rough sea", "storm": "storm", "harbour_mouth_rough": "rough harbour mouth",
        "strong_current": "strong current", "debris": "debris", "oil_spill": "oil spill",
        "boat_in_trouble": "boat in trouble", "no_fish": "no fish",
    },
    "ml": {
        "rough_sea": "കടൽക്ഷോഭം", "storm": "കൊടുങ്കാറ്റ്", "harbour_mouth_rough": "പൊഴിമുഖത്ത് ശക്തമായ തിര",
        "strong_current": "ശക്തമായ ഒഴുക്ക്", "debris": "കടലിൽ അവശിഷ്ടങ്ങൾ", "oil_spill": "എണ്ണ ചോർച്ച",
        "boat_in_trouble": "വള്ളം അപകടത്തിൽ", "no_fish": "മീൻ ഇല്ല",
    },
}

REASON = {
    "en": {
        "wave_height": "Waves reach {value} m (limit for your boat {threshold} m).",
        "wind_speed": "Wind reaches {value} km/h (limit {threshold} km/h).",
        "wind_gust": "Gusts reach {value} km/h (limit {threshold} km/h).",
        "steep_waves": "Waves are short and steep ({value} s apart).",
        "thunderstorm": "Thunderstorm expected.",
        "heavy_rain": "Heavy rain ({value} mm an hour).",
        "night": "It is dark, which is risky for small boats.",
        "official_warning": "Official warning in force: {detail}.",
        "reports": "{count} fisher report(s) nearby: {detail}.",
        "reports_rough": "{count} fishers nearby report rough conditions: {detail}.",
        "reports_unconfirmed": "{count} fisher report(s) nearby, not yet confirmed by anyone else: {detail}.",
        "data_missing": "Sea data is missing for some hours.",
        "data_stale": "The forecast could not be updated, so it may be out of date.",
        "no_window": "There is no safe stretch of 2 hours or more.",
    },
    "ml": {
        "wave_height": "തിരമാല {value} മീറ്റർ വരെ ഉയരും (നിങ്ങളുടെ വള്ളത്തിന്റെ പരിധി {threshold} മീറ്റർ).",
        "wind_speed": "കാറ്റ് മണിക്കൂറിൽ {value} കി.മീ. വരെ (പരിധി {threshold} കി.മീ.).",
        "wind_gust": "ആഞ്ഞടിക്കുന്ന കാറ്റ് മണിക്കൂറിൽ {value} കി.മീ. വരെ (പരിധി {threshold} കി.മീ.).",
        "steep_waves": "തിരകൾ അടുത്തടുത്തും കുത്തനെയുമാണ് ({value} സെക്കൻഡ് ഇടവേള).",
        "thunderstorm": "ഇടിമിന്നലോടുകൂടിയ കൊടുങ്കാറ്റിന് സാധ്യത.",
        "heavy_rain": "കനത്ത മഴ (മണിക്കൂറിൽ {value} മി.മീ.).",
        "night": "ഇരുട്ടാണ്, ചെറുവള്ളങ്ങൾക്ക് അപകടസാധ്യത കൂടുതൽ.",
        "official_warning": "ഔദ്യോഗിക മുന്നറിയിപ്പ് നിലവിലുണ്ട്: {detail}.",
        "reports": "സമീപത്ത് {count} മത്സ്യത്തൊഴിലാളി റിപ്പോർട്ട്: {detail}.",
        "reports_rough": "സമീപത്തുള്ള {count} മത്സ്യത്തൊഴിലാളികൾ കടൽ പ്രക്ഷുബ്ധമെന്ന് റിപ്പോർട്ട് ചെയ്തു: {detail}.",
        "reports_unconfirmed": "സമീപത്ത് {count} മത്സ്യത്തൊഴിലാളി റിപ്പോർട്ട്, മറ്റാരും സ്ഥിരീകരിച്ചിട്ടില്ല: {detail}.",
        "data_missing": "ചില മണിക്കൂറുകളിലെ കടൽ വിവരം ലഭ്യമല്ല.",
        "data_stale": "പ്രവചനം പുതുക്കാൻ കഴിഞ്ഞില്ല, വിവരം പഴയതായിരിക്കാം.",
        "no_window": "തുടർച്ചയായി 2 മണിക്കൂർ സുരക്ഷിതമായ സമയം ഇല്ല.",
    },
}

ANSWER = {
    "en": {
        "SAFE": "{day} is SAFE for your {boat} from {start} to {end}. Come back by {return_by}.",
        "SAFE_after": "Outside that time: {reason}",
        "CAUTION": "{day}: CAUTION for your {boat}. {reasons} If you must go, stay close to shore and come back early.",
        "UNSAFE": "{day} is UNSAFE for your {boat}. {reasons} Do not go to sea.",
    },
    "ml": {
        "SAFE": "{day} {start} മുതൽ {end} വരെ നിങ്ങളുടെ {boat} കൊണ്ട് കടലിൽ പോകാൻ സുരക്ഷിതം. {return_by}-ന് മുമ്പ് തിരിച്ചെത്തുക.",
        "SAFE_after": "ആ സമയത്തിന് പുറത്ത്: {reason}",
        "CAUTION": "{day} ജാഗ്രത വേണം. {reasons} പോകുന്നുണ്ടെങ്കിൽ തീരത്തോട് ചേർന്ന് നിൽക്കുക, നേരത്തെ മടങ്ങുക.",
        "UNSAFE": "{day} കടലിൽ പോകുന്നത് അപകടം. {reasons} കടലിൽ പോകരുത്.",
    },
}

SHORT = {
    "en": {
        "SAFE": "SAFE {start} to {end}. Back by {return_by}.",
        "CAUTION": "CAUTION. Stay near shore, return early.",
        "UNSAFE": "UNSAFE. Do not go to sea.",
    },
    "ml": {
        "SAFE": "{start} മുതൽ {end} വരെ സുരക്ഷിതം. {return_by}-ന് മുമ്പ് മടങ്ങുക.",
        "CAUTION": "ജാഗ്രത. തീരത്തോട് ചേർന്ന് നിൽക്കുക.",
        "UNSAFE": "അപകടം. കടലിൽ പോകരുത്.",
    },
}

ALERTS = {
    "en": {
        "overdue_contact": "Sea Safe: {name} has not returned. Planned return {time}. Last seen at {seen}: {link}. Sea now: {level}, waves {waves} m.",
        "overdue_check": "Are you back? You are past your return time. Tap 'I'm back' or 'More time' now, or your contacts will be alerted.",
        "overdue_fisher": "You are past your return time. Your contacts have been alerted. Tap 'I'm back' when you are ashore.",
        "all_clear": "Sea Safe: {name} is back safely ({time}). No action needed.",
        "extended": "Sea Safe: {name} is OK and has added time at sea. New return time {time}.",
        "head_back": "Head back now: {reason}",
        "sos": "SOS from {name} ({boat}). Location: {link}. Time: {time}. Sent by Sea Safe.",
        "sos_last_known": "SOS from {name} ({boat}). No GPS fix right now. LAST KNOWN position: {link}. Time: {time}. Sent by Sea Safe.",
        "sos_home": "SOS from {name} ({boat}). POSITION UNKNOWN. Home harbour: {link}. Time: {time}. Sent by Sea Safe.",
        "morning_recheck": "Forecast changed overnight. Today is now {verdict} for your boat (it was {old}). Check Sea Safe before you leave.",
        "auto_sos": "AUTOMATIC SOS from Sea Safe: {name} ({boat}) has not come back from sea and cannot be reached. "
                    "Planned return {time}, now {late} late. Last signal from the phone: {seen}. "
                    "Last known position, {km} km out: {link}. Please call the Coast Guard on 1554 and give them this position.",
        "auto_sos_fisher": "Sea Safe has sent an automatic SOS to your contacts because you are {late} late with no signal. Tap 'I'm back' as soon as you are safe.",
        "trip_reminder": "Your trip at {time}: the sea is now {verdict} for your boat. {extra}",
        "trip_reminder_unsafe": "Do not go. The planned hours are now UNSAFE: {reason}",
        "trip_reminder_ok": "Open Sea Safe and tap Start when you leave.",
        "buddy_overdue": "Buddy boat alert: {name} ({boat}) has not come back. Due {time}. Last position: {link}. You may be the nearest boat. Call 1554 if you see trouble.",
        "buddy_sos": "Buddy boat SOS: {name} ({boat}) needs help now. Position: {link}. Call the Coast Guard on 1554.",
    },
    "ml": {
        "overdue_contact": "Sea Safe: {name} തിരിച്ചെത്തിയിട്ടില്ല. മടങ്ങേണ്ട സമയം {time}. അവസാനം കണ്ടത് {seen}: {link}. കടൽ ഇപ്പോൾ: {level}, തിരമാല {waves} മീറ്റർ.",
        "overdue_check": "തിരിച്ചെത്തിയോ? മടങ്ങേണ്ട സമയം കഴിഞ്ഞു. ഇപ്പോൾ 'തിരിച്ചെത്തി' അല്ലെങ്കിൽ 'കൂടുതൽ സമയം' അമർത്തുക, ഇല്ലെങ്കിൽ ബന്ധുക്കളെ അറിയിക്കും.",
        "all_clear": "Sea Safe: {name} സുരക്ഷിതമായി തിരിച്ചെത്തി ({time}). ഒന്നും ചെയ്യേണ്ടതില്ല.",
        "extended": "Sea Safe: {name} സുരക്ഷിതനാണ്, കടലിൽ കൂടുതൽ സമയം എടുക്കുന്നു. പുതിയ മടക്ക സമയം {time}.",
        "overdue_fisher": "മടങ്ങേണ്ട സമയം കഴിഞ്ഞു. നിങ്ങളുടെ ബന്ധുക്കളെ അറിയിച്ചിട്ടുണ്ട്. കരയിലെത്തിയാൽ 'തിരിച്ചെത്തി' അമർത്തുക.",
        "head_back": "ഉടൻ മടങ്ങുക: {reason}",
        "sos": "SOS: {name} ({boat}) അപകടത്തിൽ. സ്ഥാനം: {link}. സമയം: {time}. Sea Safe അയച്ചത്.",
        "sos_last_known": "SOS: {name} ({boat}) അപകടത്തിൽ. ഇപ്പോൾ GPS ലഭ്യമല്ല. അവസാനം അറിഞ്ഞ സ്ഥാനം: {link}. സമയം: {time}. Sea Safe അയച്ചത്.",
        "sos_home": "SOS: {name} ({boat}) അപകടത്തിൽ. സ്ഥാനം അറിയില്ല. ഹാർബർ: {link}. സമയം: {time}. Sea Safe അയച്ചത്.",
        "buddy_overdue": "കൂട്ടുവള്ളം മുന്നറിയിപ്പ്: {name} ({boat}) തിരിച്ചെത്തിയിട്ടില്ല. മടങ്ങേണ്ട സമയം {time}. അവസാന സ്ഥാനം: {link}. നിങ്ങളായിരിക്കാം ഏറ്റവും അടുത്ത വള്ളം. അപകടം കണ്ടാൽ 1554 വിളിക്കുക.",
        "buddy_sos": "കൂട്ടുവള്ളം SOS: {name} ({boat}) അപകടത്തിൽ. സ്ഥാനം: {link}. കോസ്റ്റ് ഗാർഡിനെ 1554-ൽ വിളിക്കുക.",
        "morning_recheck": "രാത്രിയിൽ പ്രവചനം മാറി. ഇന്ന് നിങ്ങളുടെ വള്ളത്തിന് {verdict} (മുമ്പ് {old}). പുറപ്പെടും മുമ്പ് Sea Safe നോക്കുക.",
    },
}


def lang_of(language: Optional[str]) -> str:
    return language if language in LANGS else "en"


def _num(v) -> str:
    if v is None:
        return ""
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:g}"


def fmt_time(dt: datetime, language: str) -> str:
    """'6 AM' / '10:30 AM' in English, 'രാവിലെ 6 മണി' / 'രാവിലെ 10:30' in Malayalam."""
    lang = lang_of(language)
    h, m = dt.hour, dt.minute
    h12 = h % 12 or 12
    if lang == "en":
        suffix = "AM" if h < 12 else "PM"
        return f"{h12} {suffix}" if m == 0 else f"{h12}:{m:02d} {suffix}"
    if h < 4:
        part = "പുലർച്ചെ"
    elif h < 12:
        part = "രാവിലെ"
    elif h < 16:
        part = "ഉച്ചയ്ക്ക്"
    elif h < 19:
        part = "വൈകിട്ട്"
    else:
        part = "രാത്രി"
    return f"{part} {h12} മണി" if m == 0 else f"{part} {h12}:{m:02d}"


def reason_text(reason, language: str) -> str:
    """Text for one reason: a risk_engine.Reason or its dict form."""
    if hasattr(reason, "to_dict"):
        reason = reason.to_dict()
    lang = lang_of(language)
    template = REASON[lang].get(reason.get("text_key") or "", "")
    if not template:
        return ""
    detail = reason.get("detail") or ""
    if reason.get("factor") == "community_reports":
        detail = ", ".join(REPORT_WORD[lang].get(t, t) for t in detail.split(",") if t)
    return template.format(
        value=_num(reason.get("value")),
        threshold=_num(reason.get("threshold")),
        detail=detail,
        count=_num(reason.get("value")),
    )


def short_answer(day: dict, language: str) -> str:
    lang = lang_of(language)
    verdict = day["verdict"]
    w = day.get("window")
    if verdict == "SAFE" and w:
        return SHORT[lang]["SAFE"].format(
            start=fmt_time(w["start"], lang), end=fmt_time(w["end"], lang), return_by=fmt_time(w["return_by"], lang)
        )
    return SHORT[lang][verdict if verdict != "SAFE" else "CAUTION"]


def answer(day: dict, day_index: int, boat: str, language: str) -> str:
    """Full spoken answer for one day summary (window values are datetimes)."""
    lang = lang_of(language)
    verdict = day["verdict"]
    day_word = DAY_WORD[lang][min(max(day_index, 0), 2)]
    boat_word = BOAT_WORD[lang].get(boat, boat)
    reasons = [reason_text(r, lang) for r in day.get("reasons", [])]
    reasons = [r for r in reasons if r]
    w = day.get("window")

    if verdict == "SAFE" and w:
        parts = [
            ANSWER[lang]["SAFE"].format(
                day=day_word, boat=boat_word, start=fmt_time(w["start"], lang),
                end=fmt_time(w["end"], lang), return_by=fmt_time(w["return_by"], lang),
            )
        ]
        if reasons:
            parts.append(ANSWER[lang]["SAFE_after"].format(reason=reasons[0]))
    else:
        if not reasons:
            reasons = [REASON[lang]["no_window"]]
        key = "UNSAFE" if verdict == "UNSAFE" else "CAUTION"
        parts = [ANSWER[lang][key].format(day=day_word, boat=boat_word, reasons=" ".join(reasons[:2]))]
    parts.append(ADVISORY[lang])
    return " ".join(parts)


def detect_day(question: str) -> int:
    """Day the question is about, without the LLM: 0 today, 1 tomorrow, 2 day after."""
    q = (question or "").lower()
    if "day after" in q or "മറ്റന്നാൾ" in q or "മറ്റന്നാള്" in q:
        return 2
    if "tomorrow" in q or "നാളെ" in q:
        return 1
    return 0


def alert_lang(key: str, language: str) -> str:
    """The language an alert is actually written in: English when this one is not translated
    yet, so the words filled into it (times, boat type) must be formatted in English too."""
    lang = lang_of(language)
    return lang if key in ALERTS[lang] else "en"


def alert_text(key: str, language: str, **kwargs) -> str:
    template = ALERTS[lang_of(language)].get(key) or ALERTS["en"][key]  # untranslated keys fall back to English
    return template.format(**kwargs)


def fmt_duration(minutes: float) -> str:
    """'2 h 15 min' / '40 min'."""
    m = max(0, int(round(minutes)))
    h, m = divmod(m, 60)
    if h and m:
        return f"{h} h {m} min"
    return f"{h} h" if h else f"{m} min"
