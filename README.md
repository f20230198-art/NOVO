# Sea Safe

A voice assistant that tells a small-boat fisher whether it is safe to go to sea for their boat, then watches the trip until they are home. NOVA 2026 hackathon project.

- `backend/` FastAPI service: forecast, risk engine, advisor, trip monitor, alerts. See [backend/README.md](backend/README.md).
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

Before you start: backend running, `POST /demo/seed` done, dashboard open on the projector, phone on the same Wi-Fi with the server address set (Profile → long-press the title → Demo panel).

1. **Onboard** as a Muthalapozhi fisher: choose മലയാളം, enter a name, pick the boat with no engine, tap the **Muthalapozhi** quick-pick, add one contact.
2. **Ask.** Hold the mic and say "നാളെ രാവിലെ കടലിൽ പോകാമോ?" (in Expo Go, type it). The app speaks the answer and shows the 3-day strip. Tap **എന്തുകൊണ്ട്?** for the numbers.
3. **Switch the boat.** Profile → pick the mechanised boat → back to Home: the verdict changes. If the real sea is too calm to show a difference, set the scenario to `rough` first (UNSAFE with no engine, CAUTION with an outboard, SAFE for mechanised).
4. **Storm.** Demo panel → `storm`. The home card goes red; ask again and the answer quotes the 3 m waves.
5. **Overdue.** Set the scenario back to `calm`, ask again, tap **Start this trip**, then Demo panel → **Fast-forward my trip**. Within 60 seconds (or at once with **Run monitor now**) the overdue alert appears in the dashboard feed and the boat pulses red. With Twilio or Telegram keys it also arrives as a message.
6. **Community report.** On a second phone (same harbour), Sea Watch → **Report** → harbour mouth rough. Within 15 seconds it is on the first phone's map. Ask about today ("ഇപ്പോൾ കടലിൽ പോകാമോ?"): the answer mentions the report and the hours it covers drop to CAUTION. A report lasts 6 hours, so it does not change tomorrow's answer.
7. **SOS.** Hold the red SOS button for 2 seconds. The SMS composer opens addressed to the contacts and Coast Guard 1554, with a map link. This works with the backend switched off.

Extra moments: scenario `worsening` during a trip produces a "Head back now" alert, and posting an official warning from the dashboard (admin key `change-me` unless you set `ADMIN_KEY`) turns every boat in the area UNSAFE.

## Status

Built and tested: backend (48 tests passing, exercised against live Open-Meteo data, server run end to end with no keys) and the dashboard endpoints.

Built, typechecked and bundled, but **not yet run on a phone**: the mobile app. No APK has been built.

Not tested with real credentials: Claude explanations, Twilio SMS, Telegram, Expo push. Without keys the app uses template explanations and logs alerts as `simulated`.

The Malayalam text is a first draft and needs a native-speaker review.
