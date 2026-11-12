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

48 tests. They need no network and no keys: the weather fetch is patched to fail and the demo scenarios run on built-in placeholder rows.

## Environment (`.env`, copy from `.env.example`)

| Variable | Default | Effect when empty |
|---|---|---|
| `ANTHROPIC_API_KEY` | empty | Template explanations (English + Malayalam) instead of Claude |
| `ADMIN_KEY` | `change-me` | Needed in `X-Admin-Key` to post official warnings |
| `DATABASE_URL` | `sqlite:///./seasafe.db` | Set a `postgresql://` URL to use Postgres (also `pip install psycopg2-binary`) |
| `MONITOR_INTERVAL` | `60` | Seconds between trip-monitor passes |
| `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM` | empty | Contact alerts are logged as `simulated` instead of sent by SMS |
| `TELEGRAM_BOT_TOKEN` | empty | No Telegram alerts, no `/start` linking |

## How it fits together

- `services/risk_engine.py` is the only place a SAFE / CAUTION / UNSAFE verdict is decided. Pure functions, no I/O, covered by `tests/test_risk_engine.py`. Thresholds are in `app/thresholds.json`.
- `services/forecast.py` fetches Open-Meteo marine + weather, finds a sea point when the harbour pin is on land, caches for 30 minutes, serves the stale cache (`stale: true`) when the network fails, and applies the demo scenario.
- `services/advisor.py` runs the engine, then asks Claude (`claude-opus-5-5`, low effort, JSON output, 20 s limit) to choose the day and word the answer. The API response always carries the engine's verdict. If the wording disagrees with the verdict (keyword check, en + ml), or anything fails, the template in `templates/explanations.py` is used and `source` is `"template"`.
- `services/monitor.py` runs every `MONITOR_INTERVAL` seconds: overdue alerts, head-back alerts, 3 AM morning re-check.
- `services/notify.py` sends Expo push / Twilio SMS / Telegram and writes every attempt to the `Alert` table.

## Choices made where the spec was open

- **Day verdict.** A day is SAFE when it has a continuous SAFE window of at least 2 hours between 03:00 and 19:00 (go inside the window). With no window it is CAUTION if any hour is below UNSAFE, else UNSAFE. Any official warning that day makes the whole day UNSAFE with no window. For today, hours already over are ignored.
- **Boundaries.** Waves and wind use "greater than" (1.0 m is still SAFE for a non-motorised boat, as in the plan's table). Gusts use "greater than or equal".
- **Missing wave data** for an hour counts as CAUTION, never SAFE.
- **Reports and risk.** `no_fish` reports never change the risk. The other seven types raise nearby hours (10 km) to CAUTION from one hour before the report until it expires. Reports never produce UNSAFE.
- **Extra demo scenario `rough`** (waves 1.8 m, wind 26 km/h): UNSAFE for non-motorised, CAUTION for motorised, SAFE for mechanised. Use it for the "switch the boat" moment when the real sea is flat.
- **`worsening`** stays calm for the current and next hour slot, then jumps to 2.6–2.8 m with 58 km/h gusts. The head-back alert fires on the next monitor pass because the rise is inside the 2-hour look-ahead.
- **Offline demo.** If a demo scenario is on and Open-Meteo cannot be reached, placeholder rows are used so the demo still runs. In `real` mode with no cache the API returns 503 and the app shows its saved forecast.
- **Extra endpoints.** `POST /demo/tick` runs the monitor immediately, `POST /trips/sos` raises SOS without a trip id (creates an emergency trip if none is open), `GET /dashboard/trips` feeds the dashboard map, `GET /reports/types`, `DELETE /warnings/{id}`.
- **One open trip per fisher.** Starting a new trip closes the previous one.
- **Morning re-check.** The last day a fisher asked about is stored on the user. Between 03:00 and 06:00 local time on that day, if the verdict differs from what they were told, they get one push.
- **Auth.** `POST /users` returns a random token, sent as `X-User-Token`. The demo, alert-feed and dashboard endpoints are open on purpose for the hackathon. Do not deploy them as they are.
- **Datetimes** are stored as naive UTC. Forecast times are converted with Open-Meteo's `utc_offset_seconds`.

## Not verified / to do

- **The Claude call has not been run with a real key.** With an invalid key the request is accepted by the SDK and the code falls back to the template as designed. Test once with a real `ANTHROPIC_API_KEY` before the demo. The request uses the server-side refusal fallback beta (`server-side-fallback-2026-07-01`, `fallbacks: "default"`).
- **Twilio, Telegram and Expo push have not been tested with real credentials.**
- **The Malayalam strings need a native-speaker review** (`app/templates/explanations.py`).
- Answers in languages other than English and Malayalam fall back to English templates, and AI answers in those languages are not keyword-checked against the verdict.
