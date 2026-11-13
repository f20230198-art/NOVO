# Sea Safe backend

FastAPI + SQLModel. Runs with no API keys: explanations come from templates and alerts are logged as `simulated`.

## Run

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt        # macOS/Linux: .venv/bin/pip
.venv/Scripts/uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

- API docs: http://localhost:8001/docs
- Co-op dashboard: http://localhost:8001/dashboard
- Health: http://localhost:8001/health (shows whether AI, SMS and Telegram are configured, and the demo scenario)

`--host 0.0.0.0` matters: the phone reaches the backend over Wi-Fi at `http://<laptop-ip>:8001`. Allow port 8001 through the Windows firewall.

## Tests

```bash
.venv/Scripts/pytest -q
```

95 tests. They need no network and no keys: the weather fetch is patched to fail, the demo scenarios run on built-in placeholder rows, and the LLM is a fake where a test needs one.

## Environment (`.env`, copy from `.env.example`)

| Variable | Default | Effect when empty |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | Template explanations (English + Malayalam) instead of Claude |
| `GROQ_API_KEY`, `GROQ_API_KEY_2..4`, `GROQ_API_KEYS` (comma list), `GEMINI_API_KEY(S)` | empty | All set keys form one rotating pool (`services/llm.py`) used by the advisor (when `ANTHROPIC_API_KEY` is empty) and the voice assistant. Each call goes to the next key; a rate-limited key cools down and the same full context is retried on the next |
| `LLM_MODEL` | empty | Overrides the default model for Groq (`openai/gpt-oss-120b`) or Gemini (`gemini-2.5-flash`) |
| `ASSISTANT_PER_MINUTE`, `ASSISTANT_PER_DAY` | `6`, `120` | Voice-assistant limits per fisher (429 with `Retry-After`). Emergencies are never limited |
| `COMMUNITY_PER_MINUTE` | `8` | Chat posts per fisher per minute |
| `ADMIN_KEY` | `change-me` | Needed in `X-Admin-Key` to post official warnings and to read boat positions and the alert feed (the dashboard asks for it once) |
| `DEMO_MODE` | `true` | `false` switches off the open `/demo` endpoints (scenario, fast-forward, seed) |
| `DATABASE_URL` | `sqlite:///./seasafe.db` | Set a `postgresql://` URL to use Postgres (also `pip install psycopg2-binary`) |
| `MONITOR_INTERVAL` | `60` | Seconds between trip-monitor passes |
| `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM` | empty | Contact alerts are logged as `simulated` instead of sent by SMS |
| `TELEGRAM_BOT_TOKEN` | empty | No Telegram alerts, no `/start` linking |

## How it fits together

- `services/risk_engine.py` is the only place a SAFE / CAUTION / UNSAFE verdict is decided. Pure functions, no I/O, covered by `tests/test_risk_engine.py`. Thresholds are in `app/thresholds.json`.
- `services/forecast.py` fetches Open-Meteo marine + weather (both at the sea point, since wind over land reads lower), finds a sea point when the harbour pin is on land, caches for 30 minutes, serves the stale cache (`stale: true`, with `age_minutes`) when the network fails, and applies the demo scenario.
- `services/advisor.py` runs the engine, then asks Claude (`claude-opus-5-5`, low effort, JSON output, 10 s limit) to choose the day and word the answer. The API response always carries the engine's verdict. If the wording disagrees with the verdict (keyword check, en + ml), leaves out or changes the return-by time, or anything fails, the template in `templates/explanations.py` is used and `source` is `"template"`.
- `services/monitor.py` runs every `MONITOR_INTERVAL` seconds: overdue alerts (the fisher is asked first, then the contacts), head-back alerts, 3 AM morning re-check.
- `services/escalation.py` decides the overdue timeline: how long the fisher gets to answer "are you back?" before the contacts are told (0 in an UNSAFE sea, up to 30 min when the phone is back at the harbour), and when the **automatic SOS** fires: 90/120/180 min after overdue by boat type, only if the boat went more than 2 km out and the phone is silent for 60 min or still offshore (`thresholds.json` → `escalation`).
- `services/llm.py` is the rotating Groq/Gemini key pool. `services/rag.py` builds the assistant's corpus per request (knowledge generated from thresholds, the asking fisher's own records, public local data marked untrusted) and ranks it with BM25. `services/guard.py` screens prompt injection and fences untrusted text. `services/assistant.py` runs one turn: retrieve, one stateless LLM call, validate, then carry out allow-listed actions (schedule / confirm / cancel a trip, SOS help) with the risk engine re-checked server-side. With no key it understands the same requests by rules.
- `services/social.py` is the community: harbour chat (fishers within 50 km), events with RSVP and per-event chat, flagging (3 flags hide a message).
- New endpoints: `/assistant/chat|history|status`, `/schedule` (+ `confirm`, `cancel`, `start`), `/community/messages|events`, `POST /trips/{id}/track` (positions queued offline), `/dashboard/community`, `/demo/trips/{id}/lose-signal`.
- `services/notify.py` sends Expo push / Twilio SMS / Telegram and writes every attempt to the `Alert` table.

## Choices made where the spec was open

- **Day verdict.** A day is SAFE when it has a continuous SAFE window of at least 2 hours between 03:00 and 19:00 (go inside the window). With no window it is CAUTION if any hour is below UNSAFE, else UNSAFE. Any official warning that day makes the whole day UNSAFE with no window. For today, hours already over are ignored.
- **Boundaries.** Waves and wind use "greater than" (1.0 m is still SAFE for a non-motorised boat, as in the plan's table). Gusts use "greater than or equal".
- **Unknown is never SAFE.** Missing wave data for an hour, a forecast that could not be refreshed for more than `stale_forecast_minutes` (180), and a trip with no forecast for the next 2 hours all count as CAUTION.
- **Reports and risk.** `no_fish` reports never change the risk. The other seven types raise nearby hours (10 km) to CAUTION from one hour before the report until it expires, but only once confirmed: a net up-vote from another fisher, or two different fishers reporting (`report_min_confirmations` in `thresholds.json`; 0 restores "one report is enough"). An unconfirmed report is listed in the reasons at level SAFE. Reports never produce UNSAFE.
- **Reports and votes need a registered fisher.** One vote per fisher per report, none on your own, five reports an hour. `boat_in_trouble` and `storm` are never hidden by votes. Positions are returned rounded (`POSITION_DECIMALS` in `services/community.py`); the engine uses the exact position.
- **Overdue has two steps.** The fisher gets `overdue_check` first; the contacts get `overdue` after the escalation delay. `POST /trips/{id}/extend` ("More time") answers the check. If the contacts were already told, ending or extending the trip sends them `all_clear` / `extended`.
- **SOS says how good the position is.** `POST /trips/sos` takes `fix`: `gps`, `last_known` or `home`, and the message to the contacts is worded to match.
- **Extra demo scenario `rough`** (waves 1.8 m, wind 26 km/h): UNSAFE for non-motorised, CAUTION for motorised, SAFE for mechanised. Use it for the "switch the boat" moment when the real sea is flat.
- **`worsening`** stays calm for the current and next hour slot, then jumps to 2.6–2.8 m with 58 km/h gusts. The head-back alert fires on the next monitor pass because the rise is inside the 2-hour look-ahead.
- **Offline demo.** If a demo scenario is on and Open-Meteo cannot be reached, placeholder rows are used so the demo still runs. In `real` mode with no cache the API returns 503 and the app shows its saved forecast.
- **Extra endpoints.** `POST /demo/tick` runs the monitor immediately, `POST /trips/sos` raises SOS without a trip id (creates an emergency trip if none is open), `GET /dashboard/trips` feeds the dashboard map, `GET /reports/types`, `DELETE /warnings/{id}`.
- **One open trip per fisher.** Starting a new trip closes the previous one.
- **Morning re-check.** The last day a fisher asked about is stored on the user. Between 03:00 and 06:00 local time on that day, if the verdict differs from what they were told, they get one push.
- **Auth.** `POST /users` returns a random token, sent as `X-User-Token`. `GET /alerts` returns only the caller's own alerts. `GET /alerts/recent` and `GET /dashboard/trips` need the admin key, because they carry names, phone numbers and live positions. The `/demo` endpoints are open on purpose for the hackathon: set `DEMO_MODE=false` anywhere else, and change `ADMIN_KEY` from its default.
- **Existing database.** New tables are created and new columns added to old tables on the next start (`db._add_missing_columns`); nothing needs deleting.
- **Datetimes** are stored as naive UTC. Forecast times are converted with Open-Meteo's `utc_offset_seconds`.

## Not verified / to do

- **The Claude call has not been run with a real key.** With an invalid key the request is accepted by the SDK and the code falls back to the template as designed. Test once with a real `ANTHROPIC_API_KEY` before the demo. The request uses the server-side refusal fallback beta (`server-side-fallback-2026-07-01`, `fallbacks: "default"`).
- **Twilio, Telegram and Expo push have not been tested with real credentials.**
- **The Malayalam strings need a native-speaker review** (`app/templates/explanations.py`).
- Answers in languages other than English and Malayalam fall back to English templates, and AI answers in those languages are not keyword-checked against the verdict.
