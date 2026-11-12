You are building **Sea Safe**, a hackathon project (24-hour build, demo at 12 PM). Build the full working first version in this pass: backend, Android app (Expo), and a small co-op dashboard. Work autonomously. Do not stop to ask questions. Where something is unspecified, pick the simplest option that keeps the demo reliable, and note the choice in `backend/README.md` / `mobile/README.md`.

Before writing code, read `CLAUDE.md` (stack, design rules, commands) and `SEA-SAFE-PLAN.md` (product spec, feature priorities) in this folder. Build every **Must** feature, then as many **Should** features as you can. Skip **Could** unless everything else is done and tested. Do not build anything in the "Cut" list.

---

## 0. What the product is

A voice assistant that tells a small-boat fisher whether it is safe to go to sea **for their boat type**, gives the best time window and a return-by time, then watches the trip: it alerts family if the fisher is overdue, warns when conditions worsen, and has SOS. Fishers can post hazard reports that everyone sees, and those reports feed back into the advice.

Three main features:
1. **Ask the Sea**: voice question → verdict + window + return-by + explanation, in English or Malayalam.
2. **Trip Guardian**: start trip / I'm back / overdue alert / head-back alert / SOS.
3. **Sea Watch**: hazard reports on a map, auto-expiring, 👍/👎 votes, feeding the risk engine.

## 1. Non-negotiable rules
1. **Rules decide, the AI explains.** `risk_engine.py` is pure, deterministic and unit-tested. The LLM never chooses or changes a verdict. The API always returns the engine's verdict alongside the LLM's text.
2. Official warnings and hazard reports can only **raise** risk, never lower it.
3. SOS on the phone uses device SMS first and works with the backend down.
4. **No key is required to run.** Without `ANTHROPIC_API_KEY`, use template explanations (en + ml). Without Twilio/Telegram keys, alerts are stored with `channel="simulated"` and shown in the alert feed and dashboard.
5. Every safety screen shows: "Advisory only. Always follow official warnings (INCOIS / IMD / Coast Guard 1554)."

---

## 2. Repository layout to create

```
backend/
  app/
    main.py            # FastAPI app, CORS *, routers, lifespan starts trip monitor
    config.py          # pydantic-settings from .env
    db.py              # SQLModel engine/session, create_all on startup
    models.py          # tables (section 4)
    thresholds.json    # boat thresholds (section 5)
    routers/ users.py advisor.py trips.py reports.py warnings.py alerts.py demo.py dashboard.py
    services/
      forecast.py      # Open-Meteo fetch, sea-point search, 30-min cache, demo scenario override
      risk_engine.py   # pure functions only
      advisor.py       # Claude call + template fallback
      monitor.py       # background loop, every 60 s
      notify.py        # expo push, Twilio SMS, Telegram, simulated
      community.py     # reports, expiry, votes, nearby query
    templates/ explanations.py   # en + ml fallback text
  tests/ test_risk_engine.py test_api.py
  requirements.txt  .env.example  README.md
mobile/               # Expo app (section 8)
dashboard/index.html  # served at GET /dashboard (section 9)
```

---

## 3. Weather data (verified working, use exactly)

- Marine: `https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=wave_height,wave_period,wind_wave_height,swell_wave_height&timezone=auto&forecast_days=7`
- Weather: `https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=wind_speed_10m,wind_gusts_10m,precipitation,weather_code,is_day&wind_speed_unit=kmh&timezone=auto&forecast_days=7`
- With `timezone=auto`, times are local ISO strings without an offset (`"2026-11-12T04:00"`), and the response includes `utc_offset_seconds` (19800 for India). Convert to aware datetimes.
- **Points on land return null wave values** (the marine API snaps to a grid cell with elevation > 0). Implement `find_sea_point(lat, lon)`: if `wave_height` is all null, try offsets at 0.05°, 0.1° and 0.2° in 8 directions and use the first point with data. Cache the result per rounded (lat, lon).
- Merge both responses into hourly rows: `{time, wave_height, wave_period, wind_wave_height, swell_wave_height, wind_speed, wind_gust, precipitation, weather_code, is_day}`.
- Cache by `(round(lat,2), round(lon,2))` for 30 minutes. On network failure, serve the stale cache and mark the response `stale: true`.
- **Demo scenario override:** `POST /demo/scenario {mode: "real"|"calm"|"storm"|"worsening"}` replaces forecast values globally. `storm`: waves 3 m, gusts 60 km/h, weather_code 95. `worsening`: calm until now+2h, then waves rise to 2.8 m. This makes the demo independent of the real weather.

Test spots to seed and use: Muthalapozhi harbour mouth, Kerala (8.635, 76.775); Vizhinjam (8.375, 76.985); Kochi (9.965, 76.235); Fujairah, UAE (25.13, 56.36).

---

## 4. Data model (SQLModel)

- **User**: id, name, phone, language (`en`/`ml`/…), boat_type (`non_motorised`/`motorised`/`mechanised`), home_lat, home_lon, home_name, expo_push_token?, created_at
- **Contact**: id, user_id, name, phone, relation, telegram_chat_id?
- **Trip**: id, user_id, status (`active`/`returned`/`overdue`/`emergency`), started_at, planned_return, grace_minutes (default 30), start_lat, start_lon, last_lat?, last_lon?, last_ping_at?, forecast_snapshot (JSON text), ended_at?
- **Report**: id, user_id?, type, lat, lon, note?, anonymous (bool), created_at, expires_at, up (int), down (int)
- **Warning** (official, entered by admin): id, title, message, center_lat, center_lon, radius_km, starts_at, expires_at, source
- **Alert** (log of everything sent): id, user_id?, trip_id?, kind (`overdue`/`head_back`/`sos`/`morning_recheck`/`broadcast`), channel (`push`/`sms`/`telegram`/`simulated`), recipient, message, created_at, status

Auth: no passwords. Registration returns `user_id` + a random `token`. The app sends `X-User-Token`. Keep it simple.

---

## 5. Risk engine (`services/risk_engine.py`)

`thresholds.json`:
```json
{
  "non_motorised": {"wave_caution": 1.0, "wave_unsafe": 1.5, "wind_caution": 20, "wind_unsafe": 30, "gust_unsafe": 40},
  "motorised":     {"wave_caution": 1.5, "wave_unsafe": 2.5, "wind_caution": 30, "wind_unsafe": 40, "gust_unsafe": 55},
  "mechanised":    {"wave_caution": 2.5, "wave_unsafe": 3.5, "wind_caution": 40, "wind_unsafe": 50, "gust_unsafe": 70},
  "steep_wave_period_s": 6,
  "heavy_rain_mm": 7.5,
  "thunderstorm_codes": [95, 96, 99],
  "report_radius_km": 10,
  "warning_overrides": true,
  "_sources": "Starting values based on the Beaufort scale and the WMO sea-state table; to be validated with fishers."
}
```

Per-hour evaluation `evaluate_hour(row, boat, thresholds, warnings, reports) -> HourRisk{time, level, reasons[]}`:
- Level order: SAFE < CAUTION < UNSAFE. The final level is the max over all factors.
- Waves vs. wave_caution/unsafe. Wind vs. wind_caution/unsafe. Gust ≥ gust_unsafe → UNSAFE.
- Steep sea: wave_period < steep_wave_period_s and wave_height ≥ 0.7 × wave_caution → at least CAUTION.
- Thunderstorm code → UNSAFE. Precipitation ≥ heavy_rain_mm → at least CAUTION.
- Night (`is_day == 0`) for `non_motorised` → at least CAUTION.
- Active official warning covering the point and time → UNSAFE.
- Hazard reports within report_radius_km, not expired, with `up - down >= 0` → at least CAUTION. Two or more such reports of type `rough_sea`/`storm`/`harbour_mouth_rough` → stays CAUTION (community alone never makes it UNSAFE).
- Every reason is structured: `{factor, value, unit, threshold, level, text_key}`, e.g. `{factor: "wave_height", value: 2.1, unit: "m", threshold: 1.5, level: "UNSAFE"}`. The UI's "Why?" panel and the LLM both read these.

Higher-level functions:
- `evaluate_range(rows, …) -> list[HourRisk]`
- `best_window(hours, day, earliest=3, latest=19, min_hours=2)`: the longest continuous SAFE run that day. Return `{start, end, return_by = end - 30 min}`, or `None`.
- `day_summary(hours, day)`: worst level, SAFE hours count, best window, the main reasons.
- `best_days(hours, n_days=7)`: days ranked by SAFE daylight hours (Should feature: "best days this week").
- `confidence(hour_time, now)`: < 24 h `high`, < 72 h `medium`, else `low`.
- `trip_check(hours, now, planned_return)`: worst level between now and now+2h, used by the monitor for head-back alerts.

**Unit tests (required, all must pass):** each threshold boundary per boat type; the same conditions are SAFE for mechanised and UNSAFE for non_motorised; a warning forces UNSAFE; reports raise SAFE to CAUTION but never lower UNSAFE; best_window finds the right run and returns None when there's no safe hour; night rule; thunderstorm rule.

---

## 6. AI advisor (`services/advisor.py`)

Use the **Anthropic Python SDK** (load your `claude-api` skill for exact current usage) with model `claude-opus-5-5`, `output_config.effort: "low"` (it's a voice reply, so latency matters), and structured JSON output. Enable server-side refusal fallbacks as that skill recommends for this model. Timeout 20 s. On any error or missing key → template fallback.

Flow for `POST /advisor/ask {question, language, lat?, lon?, boat_type?}` (uses the user's saved boat and home location when omitted):
1. Fetch the forecast and run the risk engine for the next 3 days. Build compact day summaries plus hourly levels.
2. **One** Claude call. Input: question, language, boat type, location name, current local time, the 3-day summaries (levels, windows, return-by, reasons with numbers), active warnings and reports nearby. Output JSON schema:
   `{ "day_index": 0|1|2, "start_hour": int|null, "answer": string, "short_answer": string }`
   - `answer`: 2–4 short sentences in the requested language. It must state the engine's verdict for that day, the window, the return-by time and the main reason with numbers. Plain words for fishers, no jargon. `short_answer` is under 12 words, for the home screen card.
   - System prompt: the model only explains the data given. It must not invent numbers or change verdicts. If the question isn't about going to sea, answer briefly and steer back to safety. Always end with the advisory line in the user's language.
3. The server returns `{verdict (from engine for day_index), window, return_by, confidence, reasons, answer, short_answer, hourly (for the strip), source: "ai"|"template", stale}`.
4. If the model's answer contradicts the engine verdict, fall back to the template. Check this with a simple keyword test per language (e.g. the answer says "safe" while the verdict is UNSAFE).
5. Template fallback: a deterministic sentence builder in en and ml using the same data. Day detection without the LLM: "tomorrow"/"നാളെ" → 1, "day after"/"മറ്റന്നാൾ" → 2, else 0.

Malayalam words to use: SAFE = സുരക്ഷിതം, CAUTION = ജാഗ്രത, UNSAFE = അപകടം. Have the template strings reviewed by a native speaker later, and note this in the README.

Also add `GET /advisor/forecast?lat&lon&boat_type&days=3`, which returns the hourly strip + day summaries without the LLM. The home screen uses it.

---

## 7. Trips, monitor, alerts, reports

**Endpoints**
- `POST /users`, `GET /users/me`, `PUT /users/me`, `POST /users/me/contacts`, `GET /users/me/contacts`, `DELETE /users/me/contacts/{id}`
- `POST /trips/start {planned_return, lat, lon}`: saves `forecast_snapshot` (the hourly risk for the trip window, so the app can work offline)
- `POST /trips/{id}/ping {lat, lon}` · `POST /trips/{id}/end` · `POST /trips/{id}/sos {lat, lon}` · `GET /trips/active` · `GET /trips/{id}`
- `POST /reports {type, lat, lon, note?, anonymous}` · `GET /reports?lat&lon&radius_km=25` · `POST /reports/{id}/vote {dir: "up"|"down"}`
  - Report types and expiry: `rough_sea` 6h, `storm` 6h, `harbour_mouth_rough` 6h, `strong_current` 6h, `debris` 12h, `oil_spill` 24h, `boat_in_trouble` 3h, `no_fish` 24h. A report with `down - up >= 3` is hidden.
- `POST /warnings` (header `X-Admin-Key`) · `GET /warnings/active`
- `GET /alerts?user_id=` and `GET /alerts/recent` (the dashboard feed)
- `POST /demo/scenario` · `POST /demo/trips/{id}/fast-forward` (sets planned_return to now−grace−1min so the monitor fires on its next tick) · `POST /demo/seed` (seeds 4 users at the test spots, contacts, 3 hazard reports, 1 official warning, 2 active trips with one about to go overdue)
- `GET /health`

**Monitor** (`asyncio` task started in lifespan, every 60 s, with `MONITOR_INTERVAL` from env):
- Active trip past `planned_return + grace` → status `overdue` → message every contact: "{name} has not returned. Planned return {time}. Last location: https://maps.google.com/?q={lat},{lon}. Sea now: {level}, waves {x} m." Also push to the fisher. Send once (dedupe by trip + kind).
- Active trip where `trip_check` returns UNSAFE within the next 2 h → push "Head back now: {reason}" once per trip (re-arm if the level drops and rises again).
- Should: users with a trip planned for the next morning get a 3 AM re-check push when the day verdict changed since planning.

**Notify** (`services/notify.py`): `send(recipient, message, kind, …)` tries the configured channels in order: Expo push (`https://exp.host/--/api/v2/push/send`) for the fisher; Twilio SMS (REST with httpx, env `TWILIO_SID/TOKEN/FROM`) and/or Telegram (`TELEGRAM_BOT_TOKEN`, contact.telegram_chat_id) for contacts. Otherwise `simulated`. Every attempt is written to `Alert`. Optional: Telegram `/start <user_token>` deep link handler via polling, so a judge can join as a family contact live.

---

## 8. Mobile app (`mobile/`, Expo SDK latest stable, TypeScript, Expo Router)

Packages: `expo-location`, `expo-speech`, `expo-speech-recognition` (needs a dev build, see note), `expo-sms`, `expo-notifications`, `react-native-maps` (or `expo-maps`), `@react-native-async-storage/async-storage`, `i18n-js` or a small custom i18n. Configure `app.json` (android package `com.seasafe.app`, permissions: location, microphone, notifications, SMS not required with expo-sms) and `eas.json` with a `preview` profile `{ "android": { "buildType": "apk" } }`.

**Speech note:** `expo-speech-recognition` doesn't work in Expo Go. Build with a dev client (`eas build --profile development`). Also provide a **text input fallback** on the Ask screen so everything can be tested in Expo Go. Use the `ml-IN` / `en-IN` locales. TTS with `expo-speech`, language from the user setting.

API base URL from `EXPO_PUBLIC_API_URL`. All network calls are wrapped with timeout + friendly error. The last forecast is cached in AsyncStorage and shown with an "offline, last updated X" banner when the network fails.

**Screens (only these 5 + modals):**
1. **Onboarding** (first run): language (English / മലയാളം) → name + phone → boat type (3 big picture cards) → home harbour (map pin, prefilled with GPS; quick-pick for the test spots) → emergency contacts (at least 1; Coast Guard 1554 is shown and always included in SOS).
2. **Home:** large verdict card for **today** (colour + icon + `short_answer` + best window + return-by) · **3-day hourly strip** (coloured cells, tap a cell for that hour's reasons) · big **🎤 Hold to ask** button (records, shows the transcript, calls `/advisor/ask`, speaks the answer, shows the answer card with a "Why?" expander listing reasons with numbers and a "Start this trip" button that prefills return-by) · "⚠️ N hazards near you" chip → Sea Watch · official warning banner when active.
3. **Trip:** if no active trip, a start form (return time picker, defaulting to return-by). If active: status, countdown to return, current conditions for the trip location (refresh every 5 min; ping location every 5 min while the app is open), big **I'm back** button, "Report hazard" shortcut. Shows the head-back alert when received.
4. **Sea Watch:** map with report pins (icon per type, faded as they near expiry), list below sorted by distance, 👍/👎, **+ Report** opens a sheet with 8 big icon buttons, optional note, anonymous toggle, then posts at the current GPS location.
5. **Profile:** edit boat, language, harbour, contacts. A hidden **Demo panel** (long-press the app title): scenario buttons (real/calm/storm/worsening), seed data, fast-forward the active trip.

**SOS** (floating red button on every screen, **long-press 2 s** with a progress ring): get GPS → `expo-sms` composes an SMS to all contacts + 1554 with "SOS {name}, boat {type}, location https://maps.google.com/?q=lat,lon, time" → also POST `/trips/{id}/sos` (or create an emergency trip) in the background. It must work if the backend is unreachable.

**UI principles:** large touch targets (≥ 56 dp), icon + colour + short text everywhere (usable without reading), green #1B998B / amber #F4A261 / red #E63946 with icons as well (not colour alone), high contrast for bright sunlight, all strings in en + ml.

---

## 9. Co-op dashboard (`dashboard/index.html`, served at `GET /dashboard`)

One static page, no build step (Leaflet from cdnjs + vanilla JS). Polls the API every 10 s: map of active trips (green/amber/red by current level, overdue boats pulsing red), list of overdue boats, live alert feed (including `simulated` alerts, so the demo shows them), active reports, and a form to post an official warning (needs the admin key). This is the "who pays" screen for the pitch.

---

## 10. Order of work and done criteria

1. Backend skeleton, models, forecast service (with sea-point search + cache + scenario override), **risk engine + tests passing**.
2. Advisor endpoint (AI + template fallback), forecast endpoint.
3. Users/contacts, trips, monitor, notify (simulated works end to end), reports, warnings, demo endpoints + seed.
4. `test_api.py`: register → ask (template mode) → start trip → fast-forward → run one monitor tick → an `overdue` alert exists; report create/vote/expiry; the storm scenario makes the verdict UNSAFE.
5. Mobile app: onboarding → home with real data → ask (text, then voice) → trip → SOS → Sea Watch → profile/demo panel.
6. Dashboard page.
7. READMEs: setup, env vars, how to run the demo script below, how to build the APK (`npm i -g eas-cli && eas login && eas build -p android --profile preview`).

**Done means:** `pytest` passes; `uvicorn` starts with no keys set; `POST /demo/seed` then the demo script works against a phone on the same Wi-Fi; `npx tsc --noEmit` passes in `mobile/`.

**Demo script to support (put it in the root README):**
1. Onboard as a Muthalapozhi fisher with a non-motorised boat, in Malayalam.
2. Hold the mic: "നാളെ രാവിലെ കടലിൽ പോകാമോ?" → spoken answer + strip.
3. Switch the boat to mechanised → the same day changes verdict.
4. Demo panel → `storm` → the home card goes red, and the answer mentions the numbers.
5. Start a trip → fast-forward → within 60 s the overdue alert appears on the dashboard (and as SMS/Telegram if keys are set).
6. Post a "harbour mouth rough" report from a second phone → it appears on the first phone's map and in the next answer.
7. Long-press SOS → the SMS composer opens with location.

## 11. Env (`backend/.env.example`)
```
ANTHROPIC_API_KEY=
ADMIN_KEY=change-me
DATABASE_URL=sqlite:///./seasafe.db
MONITOR_INTERVAL=60
TWILIO_SID=
TWILIO_TOKEN=
TWILIO_FROM=
TELEGRAM_BOT_TOKEN=
```
Never commit real keys. Add a `.gitignore` (`.env`, `.venv`, `node_modules`, `*.db`, `.expo`).

When finished, give a short report: what's built, what's stubbed, test results, and the exact commands to run the backend, the app and the demo.
