# Sea Safe

**An AI sea-safety assistant for small-boat fishers.** Ask “Is it safe to go to sea today?” out loud, in Malayalam or English, and get a clear **SAFE / CAUTION / UNSAFE** answer for *your* boat and *your* harbour. Then Sea Safe watches the trip and raises the alarm if you don’t come home.

Built for **NOVA 2026** (24-hour hackathon). The pilot area is Vizhinjam, Kerala.

---

## Why it exists

Small-scale fishers decide every morning whether to go out, often with no reliable information:

- **Warnings don’t reach them.** Official bulletins are long, in English, and don’t give a clear yes or no for one harbour on one morning.
- **Nobody notices when they’re late.** When a boat doesn’t return, family on the shore raise the alarm hours later, with no last position.
- **What fishers see stays local.** Rough harbour mouths and hazards are seen by other fishers first, but there is no trusted way to share them.

## What it does

| Feature | What the fisher gets |
|---|---|
| **Go / no-go verdict** | SAFE, CAUTION or UNSAFE for their boat type, from live wave, wind and storm forecasts |
| **Voice assistant “Meera”** | Ask by voice in Malayalam or English. Hour-by-hour advice (“go 5–11, avoid after 2”) and she can book the trip for you |
| **Trip watch + automatic SOS** | If you’re overdue, Sea Safe asks “Are you back?”, then alerts family, buddy boats and the Coast Guard number |
| **SOS without internet** | Hold the button: an SMS with your position goes straight from the phone, even if our server is down |
| **Drift search zone** | Uses current and wind to show where a missing boat probably is now, and in +1, +3 and +6 hours |
| **Harbour-mouth check** | Estimates breaking waves at the harbour mouth, the most dangerous part of a small-boat trip |
| **Sea map** | Waves, wind and depth on a map, with a legend in metres |
| **Community** | Hazard reports, harbour chat and events. A report only counts once another fisher confirms it |
| **Family app + Ask by SMS** | Family members get alerts on their own phone; phones without data can ask by SMS |

### Safety rules we never break

1. **Rules decide, AI explains.** A tested rule engine sets the verdict (`backend/app/services/risk_engine.py`). The AI only puts it into words and can never change it.
2. **Unknown is never SAFE.** Missing or stale forecasts give CAUTION at best.
3. **Warnings only raise the risk.** Official warnings and confirmed reports can only make a verdict stricter, never more relaxed.
4. **Everything works with no API keys.** If keys are missing, answers come from templates and alerts are shown as `simulated`. The demo does not depend on any key.

## How it works

```
Open-Meteo forecasts ─┐
Official warnings ────┼─▶  Risk engine (pure rules)  ─▶  AI explains (optional)  ─▶  App · SMS · Family · Dashboard
Fisher reports ───────┘        SAFE / CAUTION / UNSAFE
```

| Part | Tech |
|---|---|
| `backend/` | Python 3.13, FastAPI, SQLModel (SQLite, or Postgres), Groq/Gemini key pool, 214 tests |
| `mobile/` | React Native + Expo (TypeScript). Speech recognition and text-to-speech run on the phone |
| `dashboard/` | One web page for the fishers’ co-op, served by the backend at `/dashboard` |
| Weather | Open-Meteo Marine + Forecast, which are free and need no key |

---

## Setup (about 5 minutes)

**You need:** Windows with [Python 3.13](https://www.python.org/downloads/) and [Node.js 18+](https://nodejs.org/), plus an Android phone with **Expo Go** installed, on the **same Wi-Fi** as the laptop.

### 1. Start the backend

From the project folder, in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-demo.ps1 -Seed
```

This sets up Python on the first run, loads demo data (`-Seed`) and **prints the address your phone needs**, for example `http://192.168.1.20:8001`. Leave it running.

> If the phone can’t connect, run it once as **Administrator** so it can open the firewall port.

### 2. Open the dashboard (optional)

Go to **http://localhost:8001/dashboard**. The admin key is `change-me`.

### 3. Start the app

```powershell
cd mobile
npm install
copy .env.example .env      # then set EXPO_PUBLIC_API_URL to the address from step 1
npx expo start --go
```

Scan the QR code with **Expo Go**.

> **Voice input** doesn’t work in Expo Go: type your questions there, or build the APK (below) to use voice input.

### Optional: AI keys

Copy `backend/.env.example` to `backend/.env` and add one or more `GROQ_API_KEY` or `GEMINI_API_KEY` values for natural AI answers. **Everything works without them.**

### Useful commands

| What | Command |
|---|---|
| Backend tests | `cd backend && .venv\Scripts\pytest -q` |
| App type check | `cd mobile && npx tsc --noEmit` |
| Run backend by hand | `cd backend && .venv\Scripts\uvicorn app.main:app --reload --host 0.0.0.0 --port 8001` |
| Build an Android APK | `cd mobile && npm i -g eas-cli && eas login && eas build -p android --profile preview` |

---

## 5-minute demo

**Before you start:** the backend is running with `-Seed`, the dashboard is on the projector, and the phones are on the same Wi-Fi.

**Simulation menu:** on the fisher phone, **long-press the “Sea Safe” title** on Home. From there you can change the weather (calm, rough, thunderstorm, cyclone…), post official warnings, fast-forward a trip or reset everything.

1. **Sign up.** Pick മലയാളം, enter a name, choose the boat with no engine, tap the **Muthalapozhi** harbour, and add one contact.
2. **Ask.** Hold the mic: “നാളെ രാവിലെ കടലിൽ പോകാമോ?” (“Can I go to sea tomorrow morning?”). Meera answers out loud. Tap **എന്തുകൊണ്ട്?** (“Why?”) to see the numbers.
3. **Change the boat.** Pick the mechanised boat in Profile. In a **Rough sea** the verdict goes from UNSAFE to SAFE, because bigger boats can handle more.
4. **Storm.** Simulation → **Cyclone**. The home card turns red and Meera explains why.
5. **Overdue.** Choose **Calm**, start a trip, then Simulation → **Fast-forward my trip**. The phone asks “Are you back?” and the family phone gets an alert.
6. **Lost at sea.** Simulation → **Lost at sea, no signal**. An automatic SOS with the last known position goes out, and the dashboard shows the **drift search zone**.
7. **Community.** On a second phone, report a rough harbour mouth. It only affects the verdict after another fisher confirms it.
8. **SOS.** Hold the red button for 2 seconds. An SMS with your position opens, ready to send, even with the backend switched off.

**Family phone:** on the first screen choose **“A family member goes fishing”**, then enter the 6-digit code from the fisher’s **Profile → Family alerts**.

---

## Project status

- Done: Backend: 214 tests passing.
- Done: App: type check and lint are clean.
- Done: Voice assistant: English and Malayalam.
- Open: Not yet tested end to end on a real phone.
- Open: The Malayalam text needs a native speaker to check it.
- Open: Twilio SMS, Telegram and push notifications have not been tried with real keys; they run as `simulated`.

## More docs

- [SEA-SAFE-PLAN.md](SEA-SAFE-PLAN.md): product spec and priorities
- [CLAUDE.md](CLAUDE.md): design rules and conventions for contributors
- [backend/README.md](backend/README.md) · [mobile/README.md](mobile/README.md)
