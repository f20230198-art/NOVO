"""Every sentence the server itself says through Meera, in English and Malayalam.

The model words replies when a key is available; these are the facts the server writes into
action replies and the no-key answers (CLAUDE.md rule 5). Placeholders are filled with values
already formatted for the language (times via explanations.fmt_time, levels via level()).
Malayalam is everyday spoken Malayalam, not formal written style. Have a native speaker review
before a real release.
"""
from __future__ import annotations

from typing import Optional

from ..templates import explanations as tx

LANGS = ("en", "ml")


def lang_of(language: Optional[str]) -> str:
    return language if language in LANGS else "en"


def level(lang: str, value: str) -> str:
    """The verdict word to say: SAFE/CAUTION/UNSAFE in English, the app's own words in Malayalam."""
    return value if lang == "en" else tx.VERDICT_WORD["ml"].get(value, value)


def duration(lang: str, minutes: float) -> str:
    if lang == "en":
        return tx.fmt_duration(minutes)
    m = max(0, int(round(minutes)))
    h, m = divmod(m, 60)
    if h and m:
        return f"{h} മണിക്കൂർ {m} മിനിറ്റ്"
    return f"{h} മണിക്കൂർ" if h else f"{m} മിനിറ്റ്"


WEEKDAYS = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "ml": ("തിങ്കളാഴ്ച", "ചൊവ്വാഴ്ച", "ബുധനാഴ്ച", "വ്യാഴാഴ്ച", "വെള്ളിയാഴ്ച", "ശനിയാഴ്ച", "ഞായറാഴ്ച"),
}
COMPASS = {
    "en": {"N": "north", "NE": "north-east", "E": "east", "SE": "south-east",
           "S": "south", "SW": "south-west", "W": "west", "NW": "north-west"},
    "ml": {"N": "വടക്ക്", "NE": "വടക്കുകിഴക്ക്", "E": "കിഴക്ക്", "SE": "തെക്കുകിഴക്ക്",
           "S": "തെക്ക്", "SW": "തെക്കുപടിഞ്ഞാറ്", "W": "പടിഞ്ഞാറ്", "NW": "വടക്കുപടിഞ്ഞാറ്"},
}

T: dict[str, dict[str, str]] = {
    "en": {
        # days
        "today": "today", "tomorrow": "tomorrow", "on_weekday": "on {weekday}",
        "at": "{day} at {time}",
        # general
        "didnt_catch": "Sorry, I didn't catch that. Could you say it again?",
        "help": ("I'm {persona}. I can tell you how the sea looks for your boat, hour by hour, plan and track your "
                 "trips, and explain SOS and the rest of Sea Safe. Try asking: how are the waves tomorrow morning?"),
        "sos": ("This is an emergency. Press and hold the red SOS button now, then call the Coast Guard on 1554. "
                "Put on your life jacket and stay with the boat."),
        "refusal": ("I can only help with sea safety, weather for your boat, planning and scheduling your trips, and "
                    "Sea Safe features. Ask me something like: can I go out tomorrow morning?"),
        "ask_times": "Sure, I can plan that. Tell me {missing}. For example, leave at 5 AM, back by 11 AM.",
        "missing_both": "when you'll leave and when you'll be back",
        "missing_back": "when you'll be back",
        # scheduling
        "sched_missing": "Sure. Which day, what time will you leave, and when will you be back? For example, tomorrow, 5 AM to 11 AM.",
        "sched_past": "{time} {day} has already gone by. Which time would you like?",
        "sched_too_long": "That's longer than {hours} hours. Can you give me a shorter trip?",
        "sched_when": "{Day}, leaving {dep}, back by {ret}",
        "sched_window": "The safe time that day is {start} to {end}, back by {ret}.",
        "sched_no_window": "There's no safe time that day for your boat.",
        "sched_unsafe": "I'm sorry, I can't schedule that. {when} is {level} for your boat. {reason} {window}",
        "sched_sea": "The sea then is {level} for your boat.",
        "sched_sea_reason": "The sea then is {level} for your boat. {reason}",
        "sched_late_note": "Later than the safe return time of {ret}.",
        "sched_question": "{when}. {sea}{extra} Shall I schedule it? Say yes to confirm.",
        "confirm_none": "There's nothing waiting for a yes right now. Tell me the day and times and I'll plan a trip.",
        "confirm_done": ("Done, your trip {day} at {time} is scheduled. I'll remind you an hour before with a fresh "
                         "forecast. Tap Start in the Trip tab when you leave."),
        "cancel_none": "You don't have a planned trip to cancel.",
        "cancel_done": "Okay, I've cancelled your trip {day} at {time}.",
        "keep_trip": "No problem, your trip keeps running. Stay safe out there.",
        "offer_declined": "Okay, I won't plan it. Just ask when you're ready.",
        # forecast
        "fc_no_hours": "I don't have forecast hours left for {day}. Ask me about another day.",
        "fc_waves": "waves about {v} metres",
        "fc_wind": "wind {v} kilometres an hour",
        "fc_gust": ", gusting {v}",
        "fc_and": " and ",
        "fc_hour": "{Day} at {time}, {detail}.",
        "fc_hour_none": "{Day} at {time}, I have no sea numbers for that hour.",
        "fc_hour_level": " That hour is {level} for your boat.",
        "fc_bar": " Crossing the harbour mouth then is {level}, so take care at the bar.",
        "fc_stale": " My forecast is out of date, so treat it as CAUTION.",
        "fc_better": " Better to go between {start} and {end}, and be back by {ret}.",
        "fc_no_safe_day": " There's no safe time {day} for your boat, so I wouldn't go out.",
        "fc_wave_range": " Waves will be {lo} metres to {hi} metres.",
        "fc_wave_one": " Waves will be {lo} metres.",
        "fc_gusts": " The strongest gusts are about {v} kilometres an hour.",
        # trips
        "tr_at_sea": "You're out on a trip right now. Your return time is {ret}.",
        "tr_overdue": " You're past your return time, so please tap I'm back or More time.",
        "tr_one": "You have one trip planned, leaving {leave}, back by {back}.",
        "tr_many": "You have {n} trips planned. The next one leaves {leave}.",
        "tr_waiting": "One of them is still waiting for your yes.",
        "tr_none": "You have no trip running and nothing planned.",
        "tr_last": "Your last trip ended {when}.",
        "tr_shall": "Shall we plan one?",
        "waiting_yes": "waiting for your yes", "scheduled": "scheduled",
        # extend / end
        "ext_no_trip": "You don't have a trip running right now, so there's nothing to extend. Start one in the Trip tab when you leave.",
        "ext_done": "Okay, I've added {dur}. Your new return time is {time}.",
        "ext_unsafe": " But please be careful, the sea in that time is {level} for your boat. {why} Start heading back as soon as you can.",
        "ext_caution": " The sea in that time is {level} for your boat, so keep an eye on it.",
        "end_no_trip": "You don't have a trip running, so there's nothing to end.",
        "end_ask": "Glad you're back! Shall I end your trip and tell your family you're safe ashore? Say yes to confirm.",
        "end_already": "That trip has already ended. Welcome back!",
        "end_done": "Done, your trip is ended and your family knows you're back. Welcome home!",
        # search
        "search_posts": " There {verb} {n} recent community post{s} about this. Open the Community tab to read what fishers are saying.",
        # day plan
        "pl_stale": ("My forecast is out of date, so I can't call any hour safe right now. Treat the sea as CAUTION "
                     "and ask me again when you have signal."),
        "pl_missing": "I don't have forecast numbers for {day}{period}, so treat it as CAUTION. Ask me again a bit later.",
        "pl_label": "{Day} {period}", "pl_label_weekday": "{Period} {day}",
        "pl_period_safe": "{label} looks {level} for your boat{waves}.",
        "pl_period_waves": ", waves about {v} metres",
        "pl_period_level": "{label} is {level} for your boat from {start}{why}.",
        "pl_go": "{Day}, go between {start} and {end}, and be back by {ret}.",
        "pl_best": "The best time {day} is between {start} and {end}, and be back by {ret}.",
        "pl_avoid": "From {start} it's {level}{why}, so I'd avoid that.",
        "pl_bar": "Take care at the harbour mouth when you leave, it's {level} then.",
        "pl_offer": "Shall I plan a trip from {dep} to {ret}?",
        "pl_no_go": "There's no safe time {day} for your boat, so I wouldn't go out. {reason}",
        "pl_wind": "the wind picks up to {v} kilometres an hour",
        "pl_wind_dir": " from the {dir}",
        "period_early morning": "early morning", "period_morning": "morning", "period_afternoon": "afternoon",
        "period_evening": "evening", "period_tonight": "tonight", "period_night": "night",
    },
    "ml": {
        "today": "ഇന്ന്", "tomorrow": "നാളെ", "on_weekday": "{weekday}",
        "at": "{day} {time}-ന്",
        "didnt_catch": "ക്ഷമിക്കണം, എനിക്ക് മനസ്സിലായില്ല. ഒന്നുകൂടി പറയാമോ?",
        "help": ("ഞാൻ {persona}. നിങ്ങളുടെ വള്ളത്തിന് കടൽ എങ്ങനെയുണ്ടെന്ന് മണിക്കൂർ തോറും പറഞ്ഞുതരാം, യാത്രകൾ പ്ലാൻ "
                 "ചെയ്യാം, SOS-ഉം Sea Safe-ന്റെ മറ്റ് കാര്യങ്ങളും വിശദീകരിക്കാം. ചോദിച്ചുനോക്കൂ: നാളെ രാവിലെ തിര എങ്ങനെയുണ്ട്?"),
        "sos": ("ഇത് അടിയന്തര സാഹചര്യമാണ്. ഉടൻ ചുവന്ന SOS ബട്ടൺ അമർത്തിപ്പിടിക്കുക, എന്നിട്ട് കോസ്റ്റ് ഗാർഡിനെ 1554-ൽ "
                "വിളിക്കുക. ലൈഫ് ജാക്കറ്റ് ഇടുക, വള്ളം വിട്ടുപോകരുത്."),
        "refusal": ("കടൽ സുരക്ഷ, നിങ്ങളുടെ വള്ളത്തിനുള്ള കാലാവസ്ഥ, യാത്ര പ്ലാൻ ചെയ്യൽ, Sea Safe-ന്റെ കാര്യങ്ങൾ — ഇവയിൽ "
                    "മാത്രമേ എനിക്ക് സഹായിക്കാൻ കഴിയൂ. ഇങ്ങനെ ചോദിക്കൂ: നാളെ രാവിലെ കടലിൽ പോകാമോ?"),
        "ask_times": "ശരി, പ്ലാൻ ചെയ്യാം. {missing} പറയൂ. ഉദാഹരണം: രാവിലെ 5 മണിക്ക് പോയി 11 മണിക്ക് തിരിച്ചെത്തും.",
        "missing_both": "എപ്പോൾ പോകും, എപ്പോൾ തിരിച്ചെത്തും എന്ന്",
        "missing_back": "എപ്പോൾ തിരിച്ചെത്തും എന്ന്",
        "sched_missing": "ശരി. ഏത് ദിവസം, എപ്പോൾ പോകും, എപ്പോൾ തിരിച്ചെത്തും? ഉദാഹരണം: നാളെ, രാവിലെ 5 മുതൽ 11 വരെ.",
        "sched_past": "{day} {time} കഴിഞ്ഞുപോയി. ഏത് സമയം വേണം?",
        "sched_too_long": "അത് {hours} മണിക്കൂറിൽ കൂടുതലാണ്. കുറച്ചുകൂടി ചെറിയ യാത്ര പറയാമോ?",
        "sched_when": "{Day} {dep}-ന് പോയി {ret}-ന് മുമ്പ് തിരിച്ചെത്തുന്ന യാത്ര",
        "sched_window": "അന്ന് സുരക്ഷിത സമയം {start} മുതൽ {end} വരെയാണ്, {ret}-ന് മുമ്പ് തിരിച്ചെത്തണം.",
        "sched_no_window": "അന്ന് നിങ്ങളുടെ വള്ളത്തിന് സുരക്ഷിതമായ സമയമില്ല.",
        "sched_unsafe": "ക്ഷമിക്കണം, ഇത് ഷെഡ്യൂൾ ചെയ്യാൻ പറ്റില്ല. {when} നിങ്ങളുടെ വള്ളത്തിന് {level} ആണ്. {reason} {window}",
        "sched_sea": "ആ സമയത്ത് കടൽ നിങ്ങളുടെ വള്ളത്തിന് {level} ആണ്.",
        "sched_sea_reason": "ആ സമയത്ത് കടൽ നിങ്ങളുടെ വള്ളത്തിന് {level} ആണ്. {reason}",
        "sched_late_note": "സുരക്ഷിതമായി തിരിച്ചെത്തേണ്ട {ret}-നേക്കാൾ വൈകിയാണ്.",
        "sched_question": "{when}. {sea}{extra} ഷെഡ്യൂൾ ചെയ്യട്ടെ? ഉറപ്പിക്കാൻ ശരി എന്ന് പറയൂ.",
        "confirm_none": "ഇപ്പോൾ ഉറപ്പിക്കാൻ ഒന്നുമില്ല. ദിവസവും സമയവും പറഞ്ഞാൽ ഞാൻ യാത്ര പ്ലാൻ ചെയ്യാം.",
        "confirm_done": ("ശരി, {day} {time}-നുള്ള നിങ്ങളുടെ യാത്ര ഷെഡ്യൂൾ ചെയ്തു. ഒരു മണിക്കൂർ മുമ്പ് പുതിയ കാലാവസ്ഥയുമായി "
                         "ഞാൻ ഓർമ്മിപ്പിക്കാം. പോകുമ്പോൾ Trip ടാബിൽ Start അമർത്തുക."),
        "cancel_none": "റദ്ദാക്കാൻ പ്ലാൻ ചെയ്ത യാത്രയൊന്നുമില്ല.",
        "cancel_done": "ശരി, {day} {time}-നുള്ള യാത്ര റദ്ദാക്കി.",
        "keep_trip": "കുഴപ്പമില്ല, നിങ്ങളുടെ യാത്ര തുടരുന്നു. സുരക്ഷിതമായിരിക്കൂ.",
        "offer_declined": "ശരി, ഞാൻ പ്ലാൻ ചെയ്യുന്നില്ല. തയ്യാറാകുമ്പോൾ ചോദിച്ചാൽ മതി.",
        "fc_no_hours": "{day} ബാക്കിയുള്ള മണിക്കൂറുകളുടെ കാലാവസ്ഥ എന്റെ കയ്യിലില്ല. മറ്റൊരു ദിവസത്തെക്കുറിച്ച് ചോദിക്കൂ.",
        "fc_waves": "തിര ഏകദേശം {v} മീറ്റർ",
        "fc_wind": "കാറ്റ് മണിക്കൂറിൽ {v} കിലോമീറ്റർ",
        "fc_gust": ", ഇടയ്ക്ക് {v} വരെ",
        "fc_and": ", ",
        "fc_hour": "{Day} {time}-ന് {detail}.",
        "fc_hour_none": "{Day} {time}-ന്റെ കടൽ വിവരങ്ങൾ എന്റെ കയ്യിലില്ല.",
        "fc_hour_level": " ആ സമയം നിങ്ങളുടെ വള്ളത്തിന് {level} ആണ്.",
        "fc_bar": " ആ സമയത്ത് പൊഴിമുഖം കടക്കുന്നത് {level} ആണ്, അഴിമുഖത്ത് ശ്രദ്ധിക്കുക.",
        "fc_stale": " എന്റെ കാലാവസ്ഥ വിവരം പഴയതാണ്, അതിനാൽ ജാഗ്രത എന്ന് കരുതുക.",
        "fc_better": " {start} മുതൽ {end} വരെ പോകുന്നതാണ് നല്ലത്, {ret}-ന് മുമ്പ് തിരിച്ചെത്തുക.",
        "fc_no_safe_day": " {day} നിങ്ങളുടെ വള്ളത്തിന് സുരക്ഷിത സമയമില്ല, ഞാനാണെങ്കിൽ പോകില്ല.",
        "fc_wave_range": " തിര {lo} മുതൽ {hi} മീറ്റർ വരെ ആയിരിക്കും.",
        "fc_wave_one": " തിര {lo} മീറ്റർ ആയിരിക്കും.",
        "fc_gusts": " ഏറ്റവും ശക്തമായ കാറ്റ് മണിക്കൂറിൽ ഏകദേശം {v} കിലോമീറ്റർ.",
        "tr_at_sea": "നിങ്ങൾ ഇപ്പോൾ യാത്രയിലാണ്. തിരിച്ചെത്തേണ്ട സമയം {ret}.",
        "tr_overdue": " തിരിച്ചെത്തേണ്ട സമയം കഴിഞ്ഞു, I'm back അല്ലെങ്കിൽ More time അമർത്തുക.",
        "tr_one": "ഒരു യാത്ര പ്ലാൻ ചെയ്തിട്ടുണ്ട്, {leave} പോയി {back}-ന് മുമ്പ് തിരിച്ചെത്തും.",
        "tr_many": "{n} യാത്രകൾ പ്ലാൻ ചെയ്തിട്ടുണ്ട്. അടുത്തത് {leave}.",
        "tr_waiting": "അതിലൊന്ന് നിങ്ങളുടെ ഉറപ്പിനായി കാത്തിരിക്കുന്നു.",
        "tr_none": "ഇപ്പോൾ യാത്രയൊന്നും നടക്കുന്നില്ല, ഒന്നും പ്ലാൻ ചെയ്തിട്ടുമില്ല.",
        "tr_last": "നിങ്ങളുടെ കഴിഞ്ഞ യാത്ര {when} അവസാനിച്ചു.",
        "tr_shall": "ഒരെണ്ണം പ്ലാൻ ചെയ്യട്ടെ?",
        "waiting_yes": "നിങ്ങളുടെ ഉറപ്പിനായി കാത്തിരിക്കുന്നു", "scheduled": "ഷെഡ്യൂൾ ചെയ്തു",
        "ext_no_trip": "ഇപ്പോൾ യാത്രയൊന്നും നടക്കുന്നില്ല, നീട്ടാൻ ഒന്നുമില്ല. പോകുമ്പോൾ Trip ടാബിൽ തുടങ്ങുക.",
        "ext_done": "ശരി, {dur} കൂട്ടി. പുതിയ തിരിച്ചെത്തൽ സമയം {time}.",
        "ext_unsafe": " പക്ഷേ ശ്രദ്ധിക്കണേ, ആ സമയത്ത് കടൽ നിങ്ങളുടെ വള്ളത്തിന് {level} ആണ്. {why} എത്രയും വേഗം തിരിച്ചുവരാൻ തുടങ്ങുക.",
        "ext_caution": " ആ സമയത്ത് കടൽ നിങ്ങളുടെ വള്ളത്തിന് {level} ആണ്, ശ്രദ്ധിച്ചിരിക്കുക.",
        "end_no_trip": "ഇപ്പോൾ യാത്രയൊന്നും നടക്കുന്നില്ല, അവസാനിപ്പിക്കാൻ ഒന്നുമില്ല.",
        "end_ask": "തിരിച്ചെത്തിയതിൽ സന്തോഷം! യാത്ര അവസാനിപ്പിച്ച് നിങ്ങൾ സുരക്ഷിതമായി കരയിലെത്തി എന്ന് കുടുംബത്തെ അറിയിക്കട്ടെ? ഉറപ്പിക്കാൻ ശരി എന്ന് പറയൂ.",
        "end_already": "ആ യാത്ര നേരത്തെ അവസാനിച്ചു. സ്വാഗതം!",
        "end_done": "ശരി, യാത്ര അവസാനിപ്പിച്ചു, നിങ്ങൾ തിരിച്ചെത്തി എന്ന് കുടുംബം അറിഞ്ഞു. വീട്ടിലേക്ക് സ്വാഗതം!",
        "search_posts": " ഇതിനെക്കുറിച്ച് കമ്മ്യൂണിറ്റിയിൽ {n} പുതിയ പോസ്റ്റുകൾ ഉണ്ട്. മത്സ്യത്തൊഴിലാളികൾ പറയുന്നത് വായിക്കാൻ Community ടാബ് തുറക്കുക.",
        "pl_stale": ("എന്റെ കാലാവസ്ഥ വിവരം പഴയതാണ്, അതിനാൽ ഇപ്പോൾ ഒരു മണിക്കൂറും സുരക്ഷിതം എന്ന് പറയാൻ പറ്റില്ല. "
                     "കടൽ ജാഗ്രത എന്ന് കരുതുക, സിഗ്നൽ കിട്ടുമ്പോൾ വീണ്ടും ചോദിക്കൂ."),
        "pl_missing": "{day}{period} കാലാവസ്ഥ കണക്കുകൾ എന്റെ കയ്യിലില്ല, അതിനാൽ ജാഗ്രത എന്ന് കരുതുക. കുറച്ചുകഴിഞ്ഞ് വീണ്ടും ചോദിക്കൂ.",
        "pl_label": "{Day} {period}", "pl_label_weekday": "{day} {period}",
        "pl_period_safe": "{label} നിങ്ങളുടെ വള്ളത്തിന് {level} ആണ്{waves}.",
        "pl_period_waves": ", തിര ഏകദേശം {v} മീറ്റർ",
        "pl_period_level": "{label} {start} മുതൽ നിങ്ങളുടെ വള്ളത്തിന് {level} ആണ്{why}.",
        "pl_go": "{Day} {start} മുതൽ {end} വരെ പോകാം, {ret}-ന് മുമ്പ് തിരിച്ചെത്തുക.",
        "pl_best": "{day} ഏറ്റവും നല്ല സമയം {start} മുതൽ {end} വരെ, {ret}-ന് മുമ്പ് തിരിച്ചെത്തുക.",
        "pl_avoid": "{start} മുതൽ {level} ആണ്{why}, അതിനാൽ ആ സമയം ഒഴിവാക്കുന്നതാണ് നല്ലത്.",
        "pl_bar": "പോകുമ്പോൾ പൊഴിമുഖത്ത് ശ്രദ്ധിക്കുക, ആ സമയത്ത് അത് {level} ആണ്.",
        "pl_offer": "{dep} മുതൽ {ret} വരെ ഒരു യാത്ര പ്ലാൻ ചെയ്യട്ടെ?",
        "pl_no_go": "{day} നിങ്ങളുടെ വള്ളത്തിന് സുരക്ഷിത സമയമില്ല, ഞാനാണെങ്കിൽ പോകില്ല. {reason}",
        "pl_wind": "കാറ്റ് മണിക്കൂറിൽ {v} കിലോമീറ്റർ വരെ കൂടും",
        "pl_wind_dir": ", {dir} ദിശയിൽ നിന്ന്",
        "period_early morning": "പുലർച്ചെ", "period_morning": "രാവിലെ", "period_afternoon": "ഉച്ചകഴിഞ്ഞ്",
        "period_evening": "വൈകുന്നേരം", "period_tonight": "ഇന്ന് രാത്രി", "period_night": "രാത്രി",
    },
}


def t(lang: str, key: str, **kw) -> str:
    """The sentence for `key` in `lang` (English when a Malayalam one is missing). `{Day}` and
    `{Period}` are filled with the capitalised form of `day` / `period`."""
    template = T[lang_of(lang)].get(key) or T["en"][key]
    for name in ("day", "period"):
        if name in kw and isinstance(kw[name], str):
            kw[name.capitalize()] = kw[name][:1].upper() + kw[name][1:]
    return template.format(**kw)
