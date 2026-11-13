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
2. **Safety wins.** Official warnings and community hazard reports can only raise risk, never lower it. Reports raise it to CAUTION at most, and only once another fisher confirms them.
3. **SOS works without the backend.** The app sends SOS via device SMS first; the backend call is best-effort. It needs a phone signal, and the message always says how good the position is; never present the home harbour as the boat's position.
4. **Unknown is never SAFE.** Missing, stale (over 3 hours) or absent forecast data is CAUTION at best. A fallback value must be labelled as one.
5. **Everything works without API keys.** No ANTHROPIC_API_KEY → template explanations. No SMS/Telegram keys → alerts are logged as `simulated` and shown in the alert feed. The demo must never break because a key is missing.
6. Thresholds live in `backend/app/thresholds.json`, not in code.
7. **Positions are private.** Boat positions, phone numbers and alert messages are only returned with the admin key or to the fisher they belong to.
8. **The assistant proposes, the server decides.** The voice assistant (`services/assistant.py`) may only pick an allow-listed action; the server re-runs the risk engine and never schedules UNSAFE hours. Facts in action replies are written by the server. Its RAG corpus (`services/rag.py`) holds only the asking fisher's own rows plus public data, never phone numbers, tokens or other fishers' positions; text written by other people is marked untrusted and fenced.
9. **Emergencies skip everything.** Distress messages bypass rate limits, the injection screen and the LLM, and get the SOS instructions at once. SOS and trip endpoints are never rate limited.
10. **Auto-SOS is slow on purpose.** Timings live in `thresholds.json` → `escalation`; the logic is pure and tested in `services/escalation.py`. Never shorten them to make a demo snappier: use `/demo/trips/{id}/lose-signal`.

## Commands
- Backend: `cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && .venv/Scripts/uvicorn app.main:app --reload --host 0.0.0.0 --port 8001`
- Backend tests: `cd backend && .venv/Scripts/pytest -q`
- Mobile: `cd mobile && npm install && npx expo start` (test with Expo Go or a dev build on a phone on the same Wi-Fi)

## Conventions
- Times: store UTC; convert using Open-Meteo's `utc_offset_seconds` for display.
- Languages: `en`, `ml` (Malayalam) required; `ta`, `hi`, `ar` optional. UI strings in `mobile/src/i18n/`.
- LLM calls go through `services/llm.py` (rotating Groq/Gemini key pool). Each call is stateless and carries its full context, so any key can serve it.
- Voice assistant is English-only for now; Malayalam UI strings fall back to English where untranslated (`ml.ts` is `Partial<Strings>`).
- Out of scope (do not build): market prices, maritime boundary alerts, IVR, gamification. (Community chat and events are now in scope: `services/social.py`.)

## Added 13 Nov (differentiators)
- **Drift search zone** (`services/drift.py`, pure): for overdue/emergency boats, current + 3% wind leeway from the last position give a centre and widening radius for now, +1, +3, +6 h. Drawn on the dashboard map. Settings under `drift` in `thresholds.json`.
- **Harbour-mouth crossing** (`risk_engine.bar_hour/bar_range/bar_windows`): estimated breaking height at the bar from wave height, period and a falling tide. Returned as `harbour_mouth` in `/advisor/forecast`. It is shown beside the verdict and does not change it. Limits under `harbour_mouth` in `thresholds.json`.
- **Sea now** (`advisor.sea_out`): wind direction, current, tide, charted depth (GEBCO via opentopodata, optional), head wind and current on the run home.
- **Buddy boats** (`routers/buddies.py`): pair by phone number; buddies get `buddy_alert` on overdue, SOS and automatic SOS.
- **Ask by SMS** (`routers/sms.py`): `POST /sms/inbound` (Twilio webhook) and `POST /sms/ask` (JSON, dashboard simulator). Template answers only.
- Mobile look: sailcloth + boat-paint palette in `lib/theme.ts`, drawn icons and the verdict illustration in `components/art.tsx`. Use `Icon`, not emoji, in new UI.
