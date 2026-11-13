# Pending tasks (13 Nov 2026)

This snapshot was pushed when work stopped. Four parallel Claude sessions were working on the app, and three were stopped part-way through.

**State at push:** `npx tsc --noEmit` passes. Backend tests: **179 passed, 1 failed** (`tests/test_assistant_tools.py::test_community_question_never_quotes_other_people_without_a_model`). Nothing has been checked end to end on a phone.

**Re-checked 13 Nov 2026 (later):** backend **214 passed, 0 failed**; `npx tsc --noEmit` and `npx expo lint` are both clean. Items ticked below were confirmed in the code; anything that needs a phone or emulator is still open.

## 1. Voice assistant "Meera" (stopped mid-edit)
Files: `backend/app/services/assistant.py`, `assistant_tools.py`, `assistant_text.py`, `rag.py`, `routers/assistant.py`, `mobile/src/app/(tabs)/assistant.tsx`, `mobile/src/lib/speech.ts`
- [x] Fix the failing test above: the no-key path must not quote other fishers' community posts.
- [ ] Finish the Malayalam replies, including the no-key template answers.
- [x] Choose an `ml-IN` TTS voice (female if available); fall back to on-screen text.
- [x] Recognise Malayalam distress words in the emergency bypass, and add tests.
- [ ] Hour-by-hour go/no-go advice ("go 5–11, avoid after 2"), with an offer to create the trip. Windows come only from `risk_engine`.
- [x] Update CLAUDE.md: the assistant is now English + Malayalam.
- [ ] Check on the emulator: typed question and spoken reply, in both languages.

## 2. Map-first Home (stopped mid-edit)
Files: `mobile/src/app/(tabs)/index.tsx`, `_layout.tsx`, `components/LeafletMap.tsx`, `MapSheet.tsx`, `lib/seaGrid.ts`, `backend/app/routers/sea_grid.py`, `services/sea_grid.py`
- [x] Translate the last string (the map's offline message inside the WebView) to Malayalam.
- [x] Add a blue-intensity layer toggle ("Waves | Wind | Depth") with a legend in metres. Wave height is required; sea depth (GEBCO) is optional.
- [ ] Check the wave texture, wind arrows and bottom sheet on the emulator in English and Malayalam (text must not clip).

## 3. Trip planning (stopped during the Malayalam check)
Files: `mobile/src/app/(tabs)/trip.tsx`, `mobile/src/components/trip/`
- [ ] Confirm that tapping an hour in the hour list sets the departure/return time (not verified).
- [ ] Take Malayalam screenshots of the planner and fix any clipping.

## 4. Demo data: done
Vizhinjam (Kerala) persona, a `kerala_week` weather scenario, community posts and hazards, and Malayalam content. Files: `services/demo_persona.py`, `demo_weather.py`, `routers/demo.py`, `mobile/src/lib/demoPersona.ts`.
- [ ] Try loading the demo on a live server and phone (not done yet).

## 5. Smaller items
- [x] `mobile/src/components/SosButton.tsx` → `sosPlacement()` `TODO(human)` (no TODO left in the code).
- [x] ESLint was set up for the first time (`eslint.config.js`). The ~26 problems in older code are fixed; `npx expo lint` is clean.
- [ ] Possible time bug: at about 10:40 AM local, the assistant said the best time starts at 12:09 PM and "it is dark". Check the UTC/local conversion.
- [ ] Do one full pass of every screen on a Galaxy M31-sized device, in both languages.

## Testing setup used
An Android emulator `Galaxy_M31` (Android 12, 1080×2340, 420 dpi) running Expo Go. Start Metro with `npx expo start --go --port 8082` (expo-dev-client is installed, so `--go` is needed for Expo Go).
