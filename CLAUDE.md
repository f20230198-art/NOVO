# Sea Safe

NOVA 2026 hackathon project (24h build). AI sea-safety assistant for small-scale fishers.
Product spec and feature priorities: [SEA-SAFE-PLAN.md](SEA-SAFE-PLAN.md). Read it before changing scope.

## Stack
- `backend/`: Python 3.13, FastAPI, SQLModel (SQLite locally, `DATABASE_URL` switches to Postgres), httpx, Anthropic Python SDK.
- `mobile/`: React Native + Expo (TypeScript, Expo Router). APK via `eas build -p android --profile preview`.
- `dashboard/`: optional single static HTML page served by the backend at `/dashboard`.
- Weather: Open-Meteo Marine + Forecast APIs (free, no key).
- Speech: on-device (expo-speech-recognition for STT, expo-speech for TTS). The server receives text only.

## Non-negotiable design rules
1. **Rules decide, AI explains.** The SAFE/CAUTION/UNSAFE verdict comes only from `risk_engine.py`, which is pure, deterministic and unit-tested. The LLM never sets or changes a verdict.
2. **Safety wins.** Official warnings and community hazard reports can only raise risk, never lower it.
3. **SOS works without the backend.** The app sends SOS via device SMS first; the backend call is best-effort.
4. **Everything works without API keys.** No ANTHROPIC_API_KEY → template explanations. No SMS/Telegram keys → alerts are logged as `simulated` and shown in the alert feed. The demo must never break because a key is missing.
5. Thresholds live in `backend/app/thresholds.json`, not in code.

## Commands
- Backend: `cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && .venv/Scripts/uvicorn app.main:app --reload --host 0.0.0.0 --port 8001`
- Backend tests: `cd backend && .venv/Scripts/pytest -q`
- Mobile: `cd mobile && npm install && npx expo start` (test with Expo Go or a dev build on a phone on the same Wi-Fi)

## Conventions
- Times: store UTC; convert using Open-Meteo's `utc_offset_seconds` for display.
- Languages: `en`, `ml` (Malayalam) required; `ta`, `hi`, `ar` optional. UI strings in `mobile/src/i18n/`.
- Out of scope (do not build): market prices, maritime boundary alerts, IVR, gamification, chat.
