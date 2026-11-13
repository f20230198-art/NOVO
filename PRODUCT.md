# Product

<!-- impeccable:product-schema 1 -->

## Platform

android

(Expo / React Native app. For the hackathon it runs in Expo Go; it can be packaged as an Android APK with EAS for production. The co-op dashboard is a separate single web page served by the backend at `/dashboard`.)

## Users

- **Small-scale fishers** in Kerala (first harbour: Muthalapozhi; also Vizhinjam, Kochi) and the UAE east coast (Fujairah). They own non-motorised, outboard-motorised or small mechanised boats. They use the app at the harbour before dawn, often in strong sunlight or darkness, sometimes with wet hands, often one-handed, on low-cost Android phones. Many have low literacy; Malayalam first, English second. Job: decide "can I go out, when, and when must I be back", then be protected while at sea.
- **Families and emergency contacts**: receive alerts (overdue, SOS with map link) by SMS when an SMS service is configured, or in the family mode of the app after linking with a 6-digit code. With neither, alerts are only logged as `simulated`.
- **Co-op / harbour staff**: watch the dashboard on a laptop or wall screen: boats at sea, overdue boats, SOS, live alerts, community reports, official warnings.
- **Hackathon judges** (NOVA 2026, Track D): see the app on a phone and the dashboard on a projector during a live demo. The redesign serves real fishers and the projector demo equally.

## Product Purpose

A voice assistant that tells a fisher whether it is safe to go to sea **for their boat, their spot and their trip**, then watches the trip until they are home. Success: a fisher gets a clear go / be careful / don't go answer with a time window in seconds, and nobody is overdue at sea without someone ashore knowing.

## Positioning

Government apps (SAMUDRA, Machli, Fisher Friend) broadcast the same forecast to everyone. Sea Safe answers each fisher's own spoken question for their boat type and watches the whole trip: advice + trip guardian + family alerts + community hazard reports in one place, including harbour-mouth danger, where many deaths happen.

## Operating Context

- Ask by holding the mic (on-device speech in Malayalam/English) or typing; the answer is spoken aloud and shown.
- Flow: Ask the Sea → Start this trip → Trip Guardian (return-by countdown, head-back alert, overdue SMS, SOS) → Sea Watch (one-tap hazard reports with expiry and 👍/👎) which feeds back into the advice.
- SOS: long-press, opens the phone's SMS composer to contacts + Coast Guard 1554 with GPS link; must work with no backend.
- Weak or no signal offshore: the trip forecast is saved on the phone.
- Demo controls (scenario switch, fast-forward, run monitor) are in the Simulation menu, opened by long-pressing the title on Home or Profile.

## Capabilities and Constraints

- The SAFE / CAUTION / UNSAFE verdict comes only from the deterministic risk engine; the AI only words the explanation. The UI must never present AI text as the decision.
- Official warnings and community reports can only raise risk.
- Every safety screen shows: "Advisory only. Always follow official warnings (INCOIS / IMD / Coast Guard 1554)."
- Everything works with no API keys (template answers, alerts marked `simulated`).
- Screens: Onboarding, six tabs (Home, Assistant, Trip, Sea Watch, Community, Profile) and the family view. Plus the dashboard page.
- Out of scope: market prices, maritime boundary alerts, IVR, gamification, catch sharing. (Community chat and events are in scope.)
- Languages: English and Malayalam required.

## Brand Commitments

Name "Sea Safe" is fixed. No logo, palette or typography is committed; the visual identity is open.

## Evidence on Hand

- Real Open-Meteo forecasts for Muthalapozhi, Vizhinjam, Kochi, Fujairah; seeded demo users (Biju, Selvan, Antony, Rashid), trips, reports and one warning via `POST /demo/seed`.
- Muthalapozhi statistic used in the pitch: about 700 accidents and 69 deaths in about 10 years (see SEA-SAFE-PLAN.md).
- No testimonials, users, partners or endorsements exist. Do not invent any.

## Product Principles

1. **The verdict is the product.** One answer, readable from arm's length in sunlight, before anything else.
2. **Works without reading.** Colour, icon, shape and voice carry the meaning; text confirms it.
3. **Safety is never ambiguous.** Danger states are never softened, hidden or styled as decoration; SOS is always one gesture away.
4. **Honest about uncertainty.** Show confidence, stale data and "advisory only" plainly.
5. **Works on a cheap phone with bad signal.**

## Accessibility & Inclusion

- Low literacy: every verdict and action pairs an icon and colour with text; never colour alone (colour-blind safe shapes/labels).
- Outdoor sunlight: high contrast, large type; touch targets well above 48dp for wet hands and one-handed use.
- Malayalam script needs taller line heights and longer strings than English.
