# Sea Safe

A voice assistant that tells a small-boat fisher whether it is safe to go to sea for their boat, then watches the trip until they are home. NOVA 2026 hackathon project.

- `backend/` FastAPI service: forecast, risk engine, advisor, voice assistant (RAG + rotating LLM keys), trip scheduling, trip monitor with automatic SOS, community chat and events, alerts. See [backend/README.md](backend/README.md).
- `mobile/` Expo (Android) app. See [mobile/README.md](mobile/README.md).
- `dashboard/` co-op dashboard, one static page served by the backend at `/dashboard`.
- Product spec: [SEA-SAFE-PLAN.md](SEA-SAFE-PLAN.md).

Rules decide, the AI explains: the SAFE / CAUTION / UNSAFE verdict comes only from `backend/app/services/risk_engine.py`. Everything runs with no API keys.

## Quick start

```bash
# 1. Backend (leave running)
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/uvicorn app.main:app --host 0.0.0.0 --port 8001

# 2. Seed demo data (another terminal), then open http://localhost:8001/dashboard
curl.exe -X POST http://localhost:8001/demo/seed

# 3. App
cd mobile
npm install
cp .env.example .env      # EXPO_PUBLIC_API_URL=http://<laptop-ip>:8001
npx expo start --go       # Expo Go; voice input needs the APK or a dev build
```

Tests: `cd backend && .venv/Scripts/pytest -q` and `cd mobile && npx tsc --noEmit`.

APK: `cd mobile && npm i -g eas-cli && eas login && eas build -p android --profile preview`.

## Demo script

Before you start: backend running, `POST /demo/seed` done, dashboard open on the projector with the admin key entered (it asks once; `change-me` unless you set `ADMIN_KEY`), phone on the same Wi-Fi with the server address set (Profile → long-press the title → Demo panel).

1. **Onboard** as a Muthalapozhi fisher: choose മലയാളം, enter a name, pick the boat with no engine, tap the **Muthalapozhi** quick-pick, add one contact.
2. **Ask.** Hold the mic and say "നാളെ രാവിലെ കടലിൽ പോകാമോ?" (in Expo Go, type it). The app speaks the answer and shows the 3-day strip. Tap **എന്തുകൊണ്ട്?** for the numbers.
3. **Switch the boat.** Profile → pick the mechanised boat → back to Home: the verdict changes. If the real sea is too calm to show a difference, set the scenario to `rough` first (UNSAFE with no engine, CAUTION with an outboard, SAFE for mechanised).
4. **Storm.** Demo panel → `storm`. The home card goes red; ask again and the answer quotes the 3 m waves.
5. **Overdue.** Set the scenario back to `calm`, ask again, tap **Start this trip**, then Demo panel → **Fast-forward my trip**. Within 60 seconds (or at once with **Run monitor now**) the phone asks "Are you back?". The family is told 0–30 minutes later (`services/escalation.py`: at once in an UNSAFE sea, longest when the phone is back at the harbour), and the alert appears in the dashboard feed while the boat pulses red. Tap **I'm back** and the family gets a "back safely" message.
5b. **Lost at sea.** Start a trip, then Demo panel → **Simulate: lost at sea, no signal**. The trip jumps past its automatic-SOS time (90/120/180 min after overdue, by boat), 7.5 km out, phone silent: the family gets an AUTOMATIC SOS with the last known position and the Coast Guard number, and the dashboard highlights it. The Trip tab shows this whole timeline in advance.
5c. **Voice assistant.** Assistant tab → hold the mic: "Schedule a trip tomorrow, leave at 6 AM, back by 11 AM" → "Yes". In `storm` it refuses UNSAFE hours. Say "my engine died, we are drifting" and it answers with the SOS steps at once.
5d. **Community.** Community tab: harbour chat with nearby fishers, and events (the seed adds a Monsoon safety meeting) with RSVP and a chat per event.
6. **Community report.** On a second phone (same harbour), Sea Watch → **Report** → harbour mouth rough. Within 15 seconds it is on the first phone's map, and the answer is unchanged: one fisher alone cannot move the verdict. On the first phone tap 👍 on the report, then ask about today ("ഇപ്പോൾ കടലിൽ പോകാമോ?"): the answer now mentions the report and the hours it covers drop to CAUTION. A report lasts 6 hours, so it does not change tomorrow's answer.
7. **SOS.** Hold the red SOS button for 2 seconds. The SMS composer opens addressed to the contacts, with a map link and a note saying whether the position is a live GPS fix. A **Call Coast Guard 1554** button appears above the SOS button. This works with the backend switched off; it does need a phone signal.

Extra moments: scenario `worsening` during a trip produces a "Head back now" alert, and posting an official warning from the dashboard (admin key `change-me` unless you set `ADMIN_KEY`) turns every boat in the area UNSAFE.

## Status

Built and tested: backend (95 tests passing), the dashboard (checked in a browser), and the voice assistant against a real Groq key and live Open-Meteo data.

Built, typechecked and bundled for Android, but **not yet run on a phone**: the mobile app. No APK has been built.

Not tested with real credentials: Claude explanations, Twilio SMS, Telegram, Expo push. Without keys the app uses template explanations, the assistant uses its rule-based path and knowledge base, and alerts are logged as `simulated`.

The voice assistant is English only for now. The Malayalam text is a first draft and needs a native-speaker review; new screens fall back to English.
