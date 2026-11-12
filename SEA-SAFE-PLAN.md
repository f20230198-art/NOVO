# Sea Safe: Build Plan (for approval)

**NOVA 2026 Hackathon · Track D (AI & Autonomous Systems) · 24 hours, ends 12 PM**
**Problem statement:** Sea Safe: *Making safer fishing decisions through real-time ocean intelligence.*
**Deliverable:** Android app (APK) + small web page for the co-op dashboard (optional)

> Please read this, then fill in **section 9 (Decisions)** at the bottom. Once both of us approve, we lock the tech stack and start the backend.

---

## 1. The app in one line

> **A voice assistant that tells a fisher whether it's safe to go out, then watches over the whole trip until they're home.**

---

## 2. Why this problem and this angle

**Why it matters**
- **Globally**, FAO officially estimates about **32,000 fishing deaths a year**. Research for Pew estimates **more than 100,000**, because deaths on small boats often go unrecorded. Most of them happen in small-scale fishing.
- **India** has about **3.5 million marine fisherfolk** (2005 census). Cyclone Ockhi (2017) killed and left missing hundreds of fishers from Kerala and Tamil Nadu.
- **Muthalapozhi harbour, Kerala**: around **700 accidents and 69 deaths in about 10 years**, mostly boats capsizing at the harbour mouth. This is our opening line in the pitch.
- **UAE**: the National Centre of Meteorology (NCM) regularly warns small-boat fishers to stay ashore in rough seas, especially off Fujairah.

**What already exists (judges will ask)**

| App | What it does | What it lacks |
|---|---|---|
| SAMUDRA (INCOIS, govt) | Ocean forecasts, wave alerts, 8 languages | Broadcast only, not personal |
| Machli (Reliance Foundation) | Audio forecast per landing site, 9 languages | Same forecast for everyone |
| Fisher Friend (MSSRF) | Fishing zones, wave and cyclone alerts | One-way, older app |
| Thoondil (Tamil Nadu govt) | Weather + fishing zones | Tamil Nadu only |
| Nabhmitra (ISRO) | Tracking + SOS | Needs a satellite device fitted on the boat |
| SafeTRX (South Africa) | Trip plan + alert to family if late | Not in India, not in local languages |

**Our gap:** every existing app does **one piece** and mostly **broadcasts**. None of them:
1. lets a fisher **ask by voice in their own language** and get advice for **their boat, their spot and their trip**,
2. combines **advice + trip safety + family alerts + community** in one place,
3. warns about **harbour mouths**, where many people actually die,
4. lets fishers share information **without giving away their fishing spots**.

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
| ③ | **Sea Watch** (community) | Fishers report hazards for everyone. Catch information is shared only within their own circle. | Live information that forecasts miss, and it feeds back into ①. |

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
| Official warning override | Official warning active → always UNSAFE | **Must** |
| Languages | Malayalam + English (more if time allows) | **Must** (2) / Should (more) |
| Confidence level | "High confidence today, low on day 3" | Should |
| Best days this week | Trip scheduling: the app picks the safest days | Should |
| Harbour-mouth warning | Extra caution for crossing the harbour mouth | Should |

### ② Trip Guardian

| Feature | What it is | Priority |
|---|---|---|
| Start trip / I'm back | One tap each, return time taken from ① | **Must** |
| SOS button | Long-press → SMS with GPS location to emergency contacts | **Must** |
| Emergency contacts | Family + co-op + Coast Guard 1554 | **Must** |
| Overdue alert | Not back by the planned time + grace period → SMS to family | **Must** |
| "Head back now" alert | Conditions getting worse during the trip → push to the fisher | Should |
| Save forecast for offline use | Trip forecast saved on the phone, readable with no signal | Should |
| Morning re-check | Forecast changed overnight → wake-up alert | Should |
| Pre-departure checklist | Life jacket, fuel, charged phone (pictures) | Could |
| Co-op dashboard (web) | Map of all boats out at sea, overdue ones in red | Could |

### ③ Sea Watch

| Feature | What it is | Priority |
|---|---|---|
| Hazard report | One-tap icon + location (+ optional photo or voice note) | **Must** |
| Hazard map / feed | Recent reports nearby | **Must** |
| Auto-expire | Reports disappear after a few hours | **Must** |
| Reports feed into ① | "2 fishers reported a rough harbour mouth" in the answer, which can raise the risk | Should |
| Confirm / dispute 👍👎 | Filters out wrong reports | Should |
| Catch info to circle only | Fish or bait sightings shared with crew or village group only | Could |
| "Bad spot" sharing | Where *not* to go, safe to share publicly | Could |
| Anonymous posting | Hide your name | Could |

**How we handle competition between fishers:** hazard reports are public because they help everyone. Catch information is **private by default** and shared only within your circle. Research shows fishers share when it **doesn't cost them their competitive edge**, readily share **bad spots** (where not to go), and value **anonymity**.

### Basics

| Feature | Priority |
|---|---|
| Onboarding: language, boat type, home harbour, emergency contacts | **Must** |
| Simple login (phone number) | **Must** |
| Disclaimer: "advisory only, follow official warnings" | **Must** |
| Fishing ban calendar (East: 15 Apr–14 Jun · West: 1 Jun–31 Jul) | Could |

### ❌ Cut (mentioned only as future scope)
Fish market prices · maritime boundary warning · satellite device integration · phone-line (IVR) version · gamification and badges · man overboard · insurance features · chat between fishers.

**Count:** 18 Must · 10 Should · 8 Could. Goal: all Musts done by about hour 14.

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
│ SOS works via phone SMS even without internet    │
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

### Three design rules
1. **Rules decide, the AI explains.** The safety verdict comes only from the risk engine. The AI can never change SAFE to UNSAFE or the other way round.
2. **Being safe wins over being convenient.** Official warnings and hazard reports can **raise** the risk level, never lower it.
3. **SOS must work when everything else fails.** It sends directly from the phone by SMS, without depending on the backend or mobile data.

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
                     ├─ conditions worsen ─▶ "Head back" push
                     ├─ past return + grace ─▶ OVERDUE ─▶ SMS family
                     └─ SOS pressed ─▶ EMERGENCY ─▶ SMS all contacts + location
```

**③ Hazard report**
```
Report → saved (type, location, time) → shown on map → feeds risk engine
→ expires after X hours (or confirmed/disputed by others)
```

### Data stored (6 tables)

| Table | Contents |
|---|---|
| **users** | name, phone, language, boat type, home harbour |
| **contacts** | user → emergency contacts (name, phone, relation) |
| **trips** | user, start, planned return, status, last location, saved forecast |
| **reports** | type, location, time, user (or anonymous), expiry, votes |
| **alerts** | log of every alert sent: what, to whom, when |
| **forecast cache** | stored forecasts, so the external API isn't called too often |

---

## 7. Safety thresholds (starting values, kept in a config file)

Based on the Beaufort scale and the WMO sea-state table. These are starting assumptions that we'd check with fishers.

| Boat type | Caution (waves) | Unsafe (waves) | Unsafe (wind) |
|---|---|---|---|
| Non-motorised (catamaran, canoe) | > 1.0 m | > 1.5 m | > 30 km/h |
| Motorised (outboard) | > 1.5 m | > 2.5 m | > 40 km/h |
| Mechanised (trawler, gillnetter) | > 2.5 m | > 3.5 m | > 50 km/h |

The risk also goes up for short, steep waves (short wave period), expected storms, and trips that run into the night.

---

## 8. Risks and our answers

| Risk | Our answer |
|---|---|
| No phone signal far out at sea (roughly 5–15 km offshore) | Save the forecast before leaving, SMS fallback, future link with the government satellite devices |
| Forecast accuracy near the coast | Confidence level, official warnings override, clear "advisory only" disclaimer |
| "Government apps already do this" | We say it first: they broadcast, we personalise and protect the whole trip |
| Fishers won't share their spots | Hazards public, catch info private, bad-spot sharing, anonymous option |
| Fake community reports | 👍/👎 voting, auto-expiry |
| Who pays? | Free for fishers. Paid by state fisheries departments, co-ops (dashboard), insurers, CSR funding (like Machli) and NGOs |

**Demo moments:** voice question in Malayalam → switch boat type and the same day changes from SAFE to UNSAFE → start a trip and fast-forward → overdue SMS lands on a judge's phone → SOS SMS with a map link → a hazard report appears live on a second phone.

---

## 9. Decisions (please fill in)

- [ ] **3 main features OK?** (Ask the Sea · Trip Guardian · Sea Watch)  Yes / Change: ______
- [ ] **Catch sharing in circles:** keep as Could / cut completely
- [ ] **Co-op dashboard:** keep as Could / move up to Should
- [ ] **Demo languages:** Malayalam + English / also add Arabic / other: ______
- [ ] **Anything to add or cut?** ______
- [ ] **Team:** who is doing what (app, backend, AI/voice, pitch)? ______

Once this is approved → **lock the tech stack → build the backend.**
