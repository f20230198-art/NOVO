# Sea Safe: Build Plan (for approval)

**NOVA 2026 Hackathon · Track D (AI & Autonomous Systems) · 24 hours, ends 12 PM**
**Problem statement:** Sea Safe: *Making safer fishing decisions through real-time ocean intelligence.*
**Deliverable:** Android app (planned as an APK; demonstrated in Expo Go, packaging as an APK is a later production step) + small web page for the co-op dashboard (optional)

> Please read this, then fill in **section 9 (Decisions)** at the bottom. Once both of us approve, we lock the tech stack and start the backend.
>
> **Revised 12 Nov 2026** after a review of the plan and the first build: statistics now carry sources, claims the app cannot back up were reworded, and the safety rules gained a fourth ("unknown is never SAFE"). What the app still cannot do is listed in **section 10**.

---

## 1. The app in one line

> **A voice assistant that tells a fisher whether it's safe to go out, then watches over the whole trip until they're home.**

---

## 2. Why this problem and this angle

**Why it matters**
- **Globally**, FAO's figure is about **32,000 fishing deaths a year** (2019, built on an older ILO estimate of 24,000). A 2022 study by the FISH Safety Foundation, commissioned by Pew, estimates **more than 100,000**, because deaths on small boats often go unrecorded. Both are estimates, not counts. Source: [Pew, 2022](https://www.pew.org/en/research-and-analysis/issue-briefs/2022/11/more-than-100000-fishing-related-deaths-occur-each-year-study-finds).
- **India** has **several million marine fisherfolk**: about 3.5 million in the 2005 CMFRI census. Later censuses (2010, 2016) exist; quote the newest national figure on the slide only after checking it in the [CMFRI census reports](https://www.cmfri.org.in/marine-fisheries-census).
- **Cyclone Ockhi (2017)**: the counts never settled. A month after the storm the government told Parliament that about 100 people were confirmed dead and several hundred fishers from Kerala and Tamil Nadu were still missing. Say "hundreds dead or missing", not one number. Source: [Arab News / AFP](https://www.arabnews.com/node/1215241).
- **Muthalapozhi harbour, Kerala**: officially **69 deaths in about 10 years**, with **more than 700 people seriously injured**, when boats capsized at the harbour mouth. Fishing communities put the deaths higher. This is our opening line in the pitch. Sources: [The News Minute](https://www.thenewsminute.com/kerala/kerala-s-crocodile-estuary-has-killed-69-fishers-10-years-who-blame-180707), [Mongabay India](https://india.mongabay.com/2024/09/a-fisher-haven-that-harbours-death/).
- **UAE**: the National Centre of Meteorology (NCM) regularly warns small-boat fishers to stay ashore in rough seas, especially off Fujairah.

**What already exists (judges will ask)**

| App | What it does | What it lacks |
|---|---|---|
| SAMUDRA (INCOIS, govt) | Ocean forecasts, wave alerts, 8 languages | Broadcast only, not personal |
| Machli (Reliance Foundation) | Audio forecast per landing site, 9 languages | Same forecast for everyone |
| Fisher Friend (MSSRF) | Fishing zones, wave and cyclone alerts | One-way, older app |
| Thoondil (Tamil Nadu govt) | Weather, fishing zones, guidance to the nearest safe shore | Tamil Nadu only |
| GEMINI (INCOIS, satellite receiver) | Warnings and fishing zones by satellite, far beyond phone coverage | Needs the device; one-way; not per boat |
| Nabhmitra (ISRO) | Tracking + SOS by satellite | Needs a satellite device fitted on the boat |
| SafeTRX (South Africa) | Trip plan + alert to family if late | Not in India, not in local languages |

**Our gap:** the apps we reviewed each do **one piece** and mostly **broadcast**. We found none that:
1. lets a fisher **ask by voice in their own language** and get advice for **their boat and their harbour**,
2. combines **advice + trip safety + family alerts + community reports** in one place,
3. lets fishers **warn each other about a rough harbour mouth** in real time (a forecast grid cannot see the harbour mouth, so this comes from fishers, not from the model),
4. keeps a fisher's **position private**: reports are shown rounded and without a name unless the fisher chooses, and boat positions are only visible to the co-op.

We are honest about the limit: Sea Safe needs a phone signal, so it covers the near-shore zone where small boats work. Beyond coverage, GEMINI and Nabhmitra are the right tools, and Sea Safe is built to sit beside them.

**Pitch line:** *"Government apps broadcast forecasts. We answer each fisher's own question and watch over the whole trip."*

---

## 3. The 3 main features

Every other feature must support one of these. If it doesn't, it's cut.

```
   ① ASK THE SEA  ──creates a trip──▶  ② TRIP GUARDIAN
   (should I go?)                      (watches me while I'm out)
         ▲                                     │
         │ reports make answers better          │ fishers at sea report what they see
         └──────────  ③ SEA WATCH  ◀────────────┘
                     (community reports)
```

| # | Main feature | What it does | Why it's essential |
|---|---|---|---|
| ① | **Ask the Sea** (AI voice advisor) | The fisher asks by voice in their own language. The app answers SAFE / CAUTION / UNSAFE **for their boat**, with the best time to leave, the latest safe return time, and the reason. | It's the core of the problem statement. No existing app gives personal, two-way advice. |
| ② | **Trip Guardian** | Start a trip, and the app watches it: warns if conditions get worse, alerts family if overdue, SOS button. | Turns advice into protection. Best demo moment. |
| ③ | **Sea Watch** (community) | Fishers report hazards for everyone, and confirm or dispute each other's reports. | Live information that forecasts miss, and it feeds back into ①. |

**Example of ①:**
> The fisher holds the mic and asks in Malayalam: *"Can I go out tomorrow morning with my small boat?"*
> App (by voice): *"Tomorrow is **safe from 4 AM to 10 AM**. After 11, waves rise to 2 metres, which is dangerous for your boat. **Come back by 10:30.** The harbour mouth will be rough after 2 PM."*
> → One tap: **Start this trip** (this hands over to ②)

---

## 4. Full feature table

**Must** = the demo fails without it · **Should** = build if time allows · **Could** = only if ahead of schedule

### ① Ask the Sea

| Feature | What it is | Priority |
|---|---|---|
| Voice question → voice answer | Hold the mic, ask, hear the answer | **Must** |
| Safety verdict for your boat | SAFE / CAUTION / UNSAFE based on boat type + forecast | **Must** |
| Best time to leave + return-by time | "Go 4–10 AM, back by 10:30" | **Must** |
| "Why?" explanation | The actual numbers behind the verdict | **Must** |
| Hourly safety strip | 3-day colour bar (green, amber, red) | **Must** |
| Official warning override | Official warning active → always UNSAFE. Warnings are entered by the co-op on the dashboard; there is no automatic feed yet | **Must** |
| Unknown is never SAFE | Missing sea data, or a forecast more than 3 hours old → CAUTION at best | **Must** |
| Answer check | The spoken answer must contain the engine's verdict word and return-by time, or the fixed template is used instead | **Must** |
| Languages | Malayalam + English (more if time allows) | **Must** (2) / Should (more) |
| Offline answer | No signal → the answer is read from the forecast saved on the phone, and says so | Should |
| Confidence level | "High confidence today, low on day 3" | Should |
| Best days this week | Trip scheduling: the app picks the safest days | Should |
| Harbour-mouth warning | From confirmed fisher reports ("harbour mouth rough"), not from the forecast | Should |

### ② Trip Guardian

| Feature | What it is | Priority |
|---|---|---|
| Start trip / I'm back | One tap each, return time taken from ① | **Must** |
| SOS button | Long-press → SMS to emergency contacts, ready to send, saying how good the position is (GPS fix, last known with its time, or unknown), then a one-tap call to the Coast Guard. Needs a phone signal | **Must** |
| Emergency contacts | Family + co-op by SMS. Coast Guard 1554 is a voice line, so it is a call button | **Must** |
| Overdue alert | Not back by the planned time + grace period → the fisher is asked first ("I'm back" / "More time"), then SMS to family with the last position and its time. Family also hears when he is back | **Must** |
| "Head back now" alert | Conditions getting worse during the trip → push to the fisher, plus an alarm set on the phone from the saved forecast, so it also rings with no signal | Should |
| Save forecast for offline use | Trip forecast saved on the phone, readable with no signal | Should |
| Morning re-check | Forecast changed overnight → wake-up alert | Should |
| Pre-departure checklist | Life jacket, fuel, charged phone (pictures) | Could |
| Co-op dashboard (web) | Map of all boats out at sea, overdue ones in red | Could |

### ③ Sea Watch

| Feature | What it is | Priority |
|---|---|---|
| Hazard report | One-tap icon + location (+ optional photo or voice note) | **Must** |
| Hazard map / feed | Recent reports nearby | **Must** |
| Auto-expire | Reports end on their own: 3 hours (boat in trouble), 6 (sea state), 12 (debris), 24 (oil spill, no fish) | **Must** |
| Reports feed into ① | A report raises the risk only once **another fisher confirms it** (a 👍, or a second fisher reporting the same). It can raise the level to CAUTION, never to UNSAFE | Should |
| Confirm / dispute 👍👎 | Registered fishers only, one vote each, not on your own report. A call for help or a storm report cannot be voted out of sight | Should |
| Private positions | Report positions are shown rounded (about 1 km; "no fish" about 11 km). Only "harbour mouth rough" and "boat in trouble" are exact | Should |
| Anonymous posting | Name hidden by default; a fisher can choose to show it | Should |
| "Bad spot" sharing | "No fish here" reports: where *not* to go, safe to share publicly | Could |
| Catch info to circle only | Fish or bait sightings shared with crew or village group only. **Not built** | Could |

**How we handle competition between fishers:** hazard reports are public because they help everyone, but one fisher alone cannot change anyone's verdict, so a made-up hazard cannot keep rivals ashore. Research shows fishers share when it **doesn't cost them their competitive edge**, readily share **bad spots** (where not to go), and value **anonymity**. Sharing catch information inside a private circle is future scope.

### Basics

| Feature | Priority |
|---|---|
| Onboarding: language, boat type, home harbour, emergency contacts | **Must** |
| Simple registration (name + phone number, kept on the phone; no password or OTP) | **Must** |
| Disclaimer: "advisory only, follow official warnings" | **Must** |
| Fishing ban calendar (East: 15 Apr–14 Jun · West: 1 Jun–31 Jul) | Could |

### ❌ Cut (mentioned only as future scope)
Fish market prices · maritime boundary warning · satellite device integration · phone-line (IVR) version · gamification and badges · man overboard · insurance features. (Chat between fishers was later moved into scope: harbour chat and events in `services/social.py`.)

**Count:** 19 Must · 11 Should · 5 Could. Goal: all Musts done by about hour 14.

---

## 5. App screens (only 5)

```
1. ONBOARDING (first time only)
   Language → Boat type → Home harbour (pin on map) → Emergency contacts

2. HOME  ← main screen
   ┌─────────────────────────────┐
   │  TODAY: 🟢 SAFE until 10 AM  │
   │  [hourly strip ▓▓▓▓░░░░]     │
   │                              │
   │        🎤  HOLD TO ASK       │  ← ① Ask the Sea
   │                              │
   │  [ ⛵ START TRIP ]            │  ← ② Trip Guardian
   │  ⚠️ 2 hazards near you        │  ← ③ Sea Watch preview
   └─────────────────────────────┘
          [🆘 SOS always visible]

3. TRIP (active trip)
   Status · return-by countdown · conditions now · [I'M BACK] · SOS

4. SEA WATCH
   Map + list of reports · [+ REPORT] (big icons)

5. PROFILE
   Boat · contacts · language · harbour
```

Outside the app: an **SMS to the family** (Must) and the **co-op dashboard web page** (Could).

**Design principles:** voice first, big icons and colours (works even if the user can't read), low data use, works offline where possible.

---

## 6. Architecture (components only; the tech stack is decided after approval)

```
┌────────────────── ANDROID APP ──────────────────┐
│ Screens · Mic/speaker · GPS · Offline cache      │
│ SOS via phone SMS: no internet, needs a signal   │
└───────────────┬──────────────────────────────────┘
                │ API
┌───────────────▼──────────── BACKEND ─────────────────────────────┐
│                                                                   │
│  ① ADVISOR PIPELINE                                               │
│   Speech→text → Understand question (AI) → RISK ENGINE (rules)    │
│   → Write explanation (AI) → Text→speech                          │
│                                                                   │
│  RISK ENGINE  (rules decide, never the AI)                        │
│   forecast + boat type + official warnings + hazard reports       │
│   → verdict per hour + best window + return-by                    │
│                                                                   │
│  ② TRIP MONITOR (background job, runs every few minutes)          │
│   checks active trips → overdue? conditions worse? → alerts       │
│                                                                   │
│  ③ COMMUNITY SERVICE                                              │
│   save reports · expiry · votes · privacy (circle-only, blurred)  │
│                                                                   │
│  NOTIFICATION SERVICE  → push to app · SMS to family              │
│                                                                   │
│  DATA FETCHER + CACHE  → marine forecast · weather · warnings     │
└───────────────┬───────────────────────────────────────────────────┘
                │
        ┌───────▼────────┐        ┌──────────────────────┐
        │   DATABASE     │        │  EXTERNAL            │
        │ users, trips,  │        │ Marine/weather API   │
        │ reports, etc.  │        │ Speech + AI APIs     │
        └────────────────┘        │ SMS gateway          │
                                  └──────────────────────┘
```

### Four design rules
1. **Rules decide, the AI explains.** The safety verdict comes only from the risk engine. The AI can never change SAFE to UNSAFE or the other way round, and its wording is checked: if the answer does not carry the engine's verdict word and return-by time, a fixed template is spoken instead.
2. **Being safe wins over being convenient.** Official warnings and hazard reports can **raise** the risk level, never lower it. An official warning makes it UNSAFE. Fisher reports can raise it to CAUTION at most, and only once a second fisher confirms, so the rule cannot be used to keep rivals ashore.
3. **SOS does not depend on our server.** It goes from the phone by SMS, with no backend and no mobile data. It still needs a phone signal, and the message always says whether the position is a live GPS fix, a last known position, or unknown.
4. **Unknown is never SAFE.** Missing sea data, a forecast that could not be refreshed for 3 hours, or no forecast for the next 2 hours of a trip all count as CAUTION.

### Main flows

**① Asking a question**
```
Voice → text → AI extracts {when, where, boat} → risk engine computes
→ AI writes answer in user's language → voice → shown with strip + "Why?"
```

**② Trip lifecycle**
```
PLANNED ──start──▶ ACTIVE ──"I'm back"──▶ RETURNED ✅
                     │
                     ├─ conditions worsen ─▶ "Head back" push + alarm set on the phone
                     ├─ "More time" ─▶ return time moves, still ACTIVE
                     ├─ past return + grace ─▶ OVERDUE ─▶ ask the fisher ─▶ (no answer) SMS family
                     │                                      └─ "I'm back" / "More time" ─▶ family told he is OK
                     └─ SOS pressed ─▶ EMERGENCY ─▶ SMS contacts + position + call 1554
```

**③ Hazard report**
```
Report → saved (type, location, time) → shown on map, position rounded
→ confirmed by another fisher → feeds risk engine (CAUTION at most)
→ expires after 3 to 24 hours by type, or is hidden when disputed
```

### Data stored (7 tables)

| Table | Contents |
|---|---|
| **users** | name, phone, language, boat type, home harbour |
| **contacts** | user → emergency contacts (name, phone, relation) |
| **trips** | user, start, planned return, status, last location, saved forecast |
| **reports** | type, location, time, user (name hidden if anonymous), expiry, vote totals |
| **votes** | one row per fisher per report, so each fisher counts once |
| **alerts** | log of every alert sent: what, to whom, when |
| **forecast cache** | stored forecasts, so the external API isn't called too often |

---

## 7. Safety thresholds (starting values, kept in a config file)

Chosen with the Beaufort scale and the WMO sea-state table as a guide. They are **our starting assumptions, not a validated standard**, and need checking with fishers and the fisheries department before anyone relies on them.

| Boat type | Caution (waves) | Unsafe (waves) | Unsafe (wind) | Unsafe (gusts) |
|---|---|---|---|---|
| Non-motorised (catamaran, canoe) | > 1.0 m | > 1.5 m | > 30 km/h | ≥ 40 km/h |
| Motorised (outboard) | > 1.5 m | > 2.5 m | > 40 km/h | ≥ 55 km/h |
| Mechanised (trawler, gillnetter) | > 2.5 m | > 3.5 m | > 50 km/h | ≥ 70 km/h |

- "Waves" is the forecast's **significant wave height** (roughly the average of the highest third). Single waves can be nearly twice as high, which is why the limits look low.
- Wind and gusts are read at the nearest **sea** point, not at the harbour, because wind over land reads lower.
- Also counted: short, steep waves (period under 6 s) → CAUTION; a thunderstorm in the forecast → UNSAFE; heavy rain (7.5 mm an hour) → CAUTION; darkness for boats with no engine → CAUTION.
- Not yet counted: two factors that are each just under their limit (they should add up), swell direction, tide and currents.

---

## 8. Risks and our answers

| Risk | Our answer |
|---|---|
| No phone signal far out at sea (roughly 5–15 km offshore) | What still works with no signal: the saved forecast, the answer read from it, and the "head back" and "are you back?" alarms set on the phone at departure. What does not: SOS and live updates, which need a signal. The overdue alert is sent by the server, so the family is still told, provided an SMS service is configured or the family phone is linked. Beyond coverage, satellite devices (GEMINI, Nabhmitra) are the answer, and we say so |
| Forecast accuracy near the coast | Confidence level, official warnings override, old or missing data is never SAFE, clear "advisory only" disclaimer |
| "Government apps already do this" | We say it first: they broadcast, we personalise and protect the whole trip |
| Fishers won't share their spots | Report positions rounded, names hidden by default, boat positions visible to the co-op only (admin key) |
| Fake community reports | One fisher alone cannot change a verdict; registered fishers only; one vote each; five reports an hour; auto-expiry |
| False overdue alarms (forgot to tap "I'm back") | The fisher is asked first and can answer with one tap; the family is told when he is back |
| "Where is the AI?" (Track D) | The AI understands a spoken question in the fisher's language and explains the answer; Trip Guardian is the autonomous part: it watches every trip, decides when to warn, whom to tell and when to escalate, with no one asking. The verdict itself is deliberately not left to an AI |
| Who pays? | Free for fishers. Paid by state fisheries departments, co-ops (dashboard), CSR funding (like Machli) and NGOs. Not insurers: trip records must never be used to refuse a claim |
| Personal data (India's DPDP Act 2023) | Location is used only for the forecast, the trip and SOS; a consent screen at onboarding is still to be added |

**Demo moments:** voice question in Malayalam → switch boat type and the same day changes from SAFE to UNSAFE (use the `rough` scenario if the real sea is calm) → start a trip and fast-forward → "Are you back?" on the phone, then the overdue alert in the dashboard feed and on a judge's phone (Telegram, or SMS to a number verified beforehand) → SOS SMS with a map link → a hazard report appears live on a second phone, and one 👍 from the first phone turns the answer to CAUTION.

---

## 9. Decisions (please fill in)

- [ ] **3 main features OK?** (Ask the Sea · Trip Guardian · Sea Watch)  Yes / Change: ______
- [ ] **Catch sharing in circles:** keep as Could / cut completely
- [ ] **Co-op dashboard:** keep as Could / move up to Should
- [ ] **Demo languages:** Malayalam + English / also add Arabic / other: ______
- [ ] **Anything to add or cut?** ______
- [ ] **Team:** who is doing what (app, backend, AI/voice, pitch)? ______
- [ ] **Demo geography:** Kerala (Muthalapozhi) / UAE (Fujairah) / both. Depends on where the judges are: ______
- [ ] **Overdue message on a judge's phone:** Telegram bot / SMS to a number verified in advance / dashboard feed only
- [ ] **How long the fisher gets to answer "are you back?"** before the family is told (`backend/app/services/escalation.py`): ______
- [ ] **Where the backend runs for the demo:** laptop on the same Wi-Fi / hosted: ______
- [ ] **Malayalam review** by a native speaker before the demo: who? ______

Once this is approved → **lock the tech stack → build the backend.**

---

## 10. Known limits (say these before a judge asks)

| Limit | Why | What would fix it |
|---|---|---|
| SOS and live alerts need a phone signal | An SMS cannot leave a phone with no signal | Pairing with a satellite device (GEMINI, Nabhmitra) |
| SOS opens the SMS app; the fisher still presses send | Android only lets the default SMS app send silently | A paired device, or approval as an emergency app |
| Position updates pause when the screen is off | The app only has location permission while in use | Background location with a foreground service |
| The harbour mouth is not forecast | Forecast grids are kilometres wide; a harbour mouth is metres | Tide and swell-direction data, a local sensor or camera |
| Official warnings are typed in by the co-op | No machine-readable feed is connected | Connect a public alert feed (for example NDMA's) |
| Thresholds are assumptions | No field validation yet | Review with fishers and the fisheries department |
| Voice needs data | Speech recognition for Malayalam runs online | An on-device Malayalam model |
| No password or OTP | Kept simple for the hackathon | Phone-number verification |
| Multi-day trawler trips and crews sharing one boat | One trip belongs to one phone, and the safe window is daytime only | Boat-level trips with a crew list |
| Malayalam text is a first draft | Written without a native reviewer | Review before any real use |
