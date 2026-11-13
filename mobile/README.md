# Sea Safe mobile app

Expo SDK 58, TypeScript, Expo Router. Screens are in `src/app/`, shared code in `src/lib/` and `src/components/`, strings in `src/i18n/` (English + Malayalam).

## Run on a phone (same Wi-Fi as the backend)

```bash
cd mobile
npm install
cp .env.example .env        # set EXPO_PUBLIC_API_URL=http://<laptop-ip>:8001
npx expo start --go         # scan the QR code with Expo Go
```

`--go` is needed because `expo-dev-client` is installed; without it the QR code targets a development build.

The server address can also be changed on the phone: **Server settings** on the first screen, or **long-press the title on Home or Profile → Simulation menu → Server settings**. Use this when the laptop's IP changes.

## What works where

| Feature | Expo Go | Dev build / APK |
|---|---|---|
| Typed question, spoken answer (TTS) | yes | yes |
| Voice question (hold the mic) | no, falls back to typing | yes |
| SOS SMS composer, GPS, maps, reports, trips | yes | yes |
| Local notification for head-back / overdue | no, in-app banner only | yes |
| Remote push from the server | no | only with an EAS project and FCM set up |

Voice input needs a development build or the APK, because `expo-speech-recognition` has native code that Expo Go does not include.

## Build

For the hackathon the app runs in **Expo Go** (see "Run on a phone" above); no APK has been built. The project is a standard Expo app with `eas.json` profiles, so packaging it is a build step, not a code change:

```bash
npx eas-cli@latest login
npx eas-cli@latest build -p android --profile development   # dev client: voice input with live reload
npx eas-cli@latest build -p android --profile preview       # installable APK
npx eas-cli@latest build -p android --profile production    # Play Store bundle
```

Building locally on Windows (`npx expo prebuild -p android`, then `gradlew assembleRelease`) works only from a short path such as `C:\ss`: the native C++ build fails past Windows' 260-character path limit.

`EXPO_PUBLIC_API_URL` is baked in at build time. Set it in `.env` before building, or change it in the app afterwards (Server settings).

Typecheck: `npx tsc --noEmit`.

## Choices made where the spec was open

- **Map: Leaflet + OpenStreetMap in a WebView**, not `react-native-maps`. `react-native-maps` needs a Google Maps API key in a standalone Android build; this needs no key and behaves the same in Expo Go and the APK. It needs an internet connection for tiles.
- **Return time picker** is a large time display with −30 / +30 minute buttons (no native picker dependency, big touch targets).
- **Location rule.** For forecasts, trips and hazard reports the app uses GPS when the phone is within 100 km of the home harbour, otherwise the home harbour. This keeps a demo held away from the coast working. SOS always sends the real GPS position.
- **Onboarding works offline.** The profile and contacts are saved on the phone first; registration with the server is retried on the next start. If the server database was reset, the app registers again by itself.
- **Head-back and overdue** reach the phone by polling the trip every 20 seconds, so they show without push notifications.
- **Cleartext HTTP** is enabled for Android (`expo-build-properties`) because the demo backend is `http://` on the LAN.
- **Simulation menu** has an extra `rough` scenario and a "Run monitor now" button besides what the spec lists.
- `.npmrc` sets `legacy-peer-deps=true`: without it `npm install` fails on a `react-dom` peer-version mismatch inside Expo Router's dependencies.

## Not verified / to do

- **Tested in Expo Go only.** It typechecks, lints clean and the main flows were tried in Expo Go on a Galaxy M31 (see the root README). Voice input and local notifications only run in a native build, which has not been made yet.
- **No APK has been built.** The app runs in Expo Go; see Build.
- **The Malayalam strings need a native-speaker review** (`src/i18n/ml.ts`).
- Malayalam speech needs the Malayalam voice and language pack installed in the phone's Google speech services.
- Pre-departure checklist, catch sharing and the fishing-ban calendar (all "Could") are not built.
