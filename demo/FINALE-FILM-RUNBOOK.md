# EKYATRA Saathi — finale film runbook

A re-runnable, step-by-step script for recording the 8–9 minute descriptive demo.
Every step has an id. Say **"next"** (or **"go S7"**) and Claude does that step's
actions, records the named clip, checks it and stops.

Only deployed screens are used:

| Screen | Where | Recorded by |
|---|---|---|
| **Console** (control centre) | `https://ekyatra-saathi-control-centre.onrender.com` | Browser pane / Playwright, 1600×1000 |
| **HMS** (OpenEMR, the hospital) | `http://8.231.81.219:8300` | Browser pane / Playwright, same size |
| **Phone** (family app, Samsung SM-S928B) | `org.ekyatra.saathi`, built against `https://ekyatra-saathi-ueoa.onrender.com/api` | `adb screenrecord` (≤3 min per clip) |
| **Partner app** (cab / stay jobs) | `https://ekyatra-saathi-partner.onrender.com` | Browser pane |
| API | `https://ekyatra-saathi-ueoa.onrender.com/api` | — |

Clips land in `~/Downloads/demo-recordings/finale/<step-id>-<name>.mp4`.
The Remotion project lives in `demo/film/` and the voice is Kokoro
(`~/.venvs/kokoro`, model in `~/.cache/kokoro`).

**"Front" / "back".** Each step names the screen that is *front*. In the edit,
the front screen fills the frame. The others shrink into a side rail, or
leave with a slide and blur. When a step says *front: Phone*, the phone
recording is the hero and the Console sits small beside it.

---

## Part 0 — Reset (run before every take, safe to repeat)

| Id | Action | Who | Check |
|---|---|---|---|
| R1 | Wake all four Render services (`/api/health`, Console, Partner, Family). The first hit after sleep takes ~60 s. | Claude | `health.status == ok`, `ledger_intact == true` |
| R2 | **OpenEMR:** delete leave entries left by earlier takes: `DELETE FROM openemr_postcalendar_events WHERE pc_hometext LIKE '%oncology leave%'` on the VM over `gcloud compute ssh saathi-hms` (needs `CLOUDSDK_PYTHON=python3.11`). | Claude, **after you approve** | OpenEMR day view shows no leave on the take's day |
| R3 | **OpenEMR:** re-set any demo appointment a write-back moved. Earlier takes left `rebook:old-slot-left-open`, so cancel the old slot in the calendar. | You or Claude | Each EKY family has exactly one future appointment |
| R4 | **Saathi:** `POST /api/live/control {"action":"clear"}`. This forgets questions asked, readings waiting, option searches and connector memory. It deletes no patient, step or plan. | Claude | `GET /questions/waiting` → `[]`, `GET /requests/waiting` → `[]` |
| R5 | **Saathi records (Supabase):** remove demo leftovers only: the stray `MRI-2 machine_down "test"` disruption, option sets and approvals from earlier takes, demo family messages and unconfirmed spend entries for the EKY/SHOW families. **The hash-chained evidence ledger is never touched.** | Claude, **after you approve** | `GET /disruptions` shows none from earlier takes |
| R6 | Hospital rules saved for `TMH-MUM` (`used_by_planner: true`). | Claude | `GET /policy/TMH-MUM` |
| R7 | Phone: unlock, stay-awake on, `adb shell svc power stayon usb`, notifications cleared, app force-stopped then opened on the family picker. | Claude | Screenshot shows the picker |
| R8 | Sign into OpenEMR in the browser pane. **You type the password.** Claude never enters it. | You | Calendar visible |

---

## Part 1 — The film, chapter by chapter

Times are targets for the cut (total ≈ 8:40). "Illustration" means a
Remotion-drawn animated card (SVG), not a screen recording.

### C0 · Logo — 0:00–0:08
| Id | Front | Action | Narration |
|---|---|---|---|
| S0 | Illustration | Saathi mark draws on, then the wordmark "EKYATRA Saathi" and the line *"The patient's journey, between hospitals."* | *(music only, then)* "This is EKYATRA Saathi." |

### C1 · The problem — 0:08–0:50
| Id | Front | Action | Narration (draft) |
|---|---|---|---|
| S1 | Illustration | Map of India. Lines fly from Gaya, Darbhanga, Bhubaneswar and Madurai into a handful of cancer centres (Mumbai, Delhi, Kolkata, Chennai). Distances count up: 1,000 km, 40 hours. | "Most cancer care in India sits in a few cities. Most patients don't. A family from Gaya travels a thousand kilometres, and two days, to reach a hospital in Mumbai." |
| S2 | Illustration | A hospital and a family as two separate boxes, with no line between them. Inside the hospital: a calendar changes (doctor on leave, scanner down, report late). The family's box still reads "Train, Thursday". | "The hospital runs on its own system. When a doctor takes leave, a scanner breaks or a report runs late, the hospital knows. The family on the train doesn't." |

### C2 · What it costs cancer patients — 0:50–1:35
| Id | Front | Action | Narration |
|---|---|---|---|
| S3 | Illustration | Three counters: a wasted journey (₹ for travel, lost wages, nights in the city), the treatment gap (days between doses stretching), and dropout (a figure fading from a line of visits). | "For a cancer patient, a wasted journey isn't an inconvenience. It's money the family borrowed, wages lost, and a dose that slips. Long treatment is where families drop out, and money and distance are why." |
| S4 | Illustration | Pull-quote card: *"Nobody tells the family. Nobody ever does."* | "Nobody tells the family, because nobody's job is the space between the hospital and the home. That's the space Saathi works in." |

### C3 · One network — 1:35–2:05
| Id | Front | Action | Narration |
|---|---|---|---|
| S5 | Illustration | Hub diagram. Saathi in the centre. Around it, nodes appear one by one: hospitals, clinics and labs, pharmacies and Jan Aushadhi, rail, bus, cabs, ambulances, stays and dharamshalas, medical-equipment suppliers for home setup, insurers and scheme desks. Families sit on the outer ring. | "Saathi joins everyone a cancer journey runs through into one network: hospitals and clinics, labs and pharmacies, rail, bus and cabs, places to stay, equipment for care at home, and the scheme desks that pay. Then it puts the family in the middle." |

### C4 · Registering the network — 2:05–3:05
| Id | Front | Clip | Action | Narration |
|---|---|---|---|---|
| S6 | Console | `S6-registries` | Registries → Hospitals (Tata Memorial, Mumbai), then Centres, Clinicians, Resources (MRI-1, MRI-2, echo, dialysis), Staff accounts. | "It starts with registration. Each hospital is registered with its centres, its doctors and the machines a patient depends on." |
| S7 | Console | `S7-directory` | Directory: filter through all 11 kinds (hospital, lab, pharmacy, medicine distributor, equipment distributor, shop, cab, travel, hotel/stay, insurer, ambulance). Open one cab and one equipment supplier. | "Then everyone else. Forty organisations across eleven kinds: labs, pharmacies, cabs, rail and bus partners, stays, ambulances, insurers, and suppliers who set up oxygen or a hospital bed at home." |
| S8 | Console | `S8-config` | Configuration → TMH-MUM rules: what the planner may and may not do, and what is switched on. | "Each hospital sets its own rules, and the agents work inside them." |
| S9 | Partner app | `S9-partner` | Partner web: the jobs list a cab or stay partner sees, labelled sandbox. | "Partners get a simple job list. They see the trip and the dates, never the diagnosis or the family's budget." |
| S10 | Illustration | — | Pattern card: register → connect → watch. Shows the Beckn/ONDC-style network endpoint and FHIR. | "Every partner plugs in the same way, over open standards: FHIR for hospitals, a Beckn-style network for travel and stay." |

### C5 · Bringing a family in — 3:05–3:40
| Id | Front | Clip | Action | Narration |
|---|---|---|---|---|
| S11 | Console | `S11-onboarding` | Onboarding: one family's profile sections, documents verified, consent requests and grants (ABHA-shaped), the access log. | "Taking a family on asks only what only the family knows: language, consent and who travels. Everything clinical comes from the hospital." |
| S12 | Phone | `S12-picker` | Phone: family picker → choose a family → app opens in their language (Hindi, Bengali, Tamil, Odia, English). | "The family's app opens in their own language, in five scripts, and it speaks too." |

### C6 · A real hospital system — 3:40–4:10
| Id | Front | Clip | Action | Narration |
|---|---|---|---|---|
| S13 | HMS | `S13-openemr` | OpenEMR calendar with the EKY families' appointments. | "This is OpenEMR, a real open-source hospital system, unmodified. Nothing of ours is installed in it. Saathi reads it over the standard FHIR API and writes approved bookings back the same way." |
| S14 | Console | `S14-hospital-now` | Hospitals right now: the connector is live (appointments read, leaves seen) and resources are up or down. | "The Console reads that hospital live: every appointment, every leave, every machine out of service." |

### C7 · Agents, governed by people — 4:10–4:50
| Id | Front | Clip | Action | Narration |
|---|---|---|---|---|
| S15 | Illustration | — | Agents as lanes: hospital watcher → reader of the family's words → planner → readiness gate → message guard. Two human gates are marked: the navigator agrees with the reading, and the navigator approves the plan. | "Behind this is a team of agents. One watches the hospital. One reads what families say. One plans. One decides whether a family is ready to travel. One checks every message before it goes out. Two things always need a person: agreeing with what the family meant, and approving a change to a booking." |
| S16 | Console | `S16-today` | Today: what needs a person now, auto-sorted. | "The desk sees only what needs a person, sorted by who's hit hardest." |

### C8 · Maps and data — 4:50–5:25
| Id | Front | Clip | Action | Narration |
|---|---|---|---|---|
| S17 | Phone | `S17-journey` | Plan → journey card: the long leg as two stations plus a hand-off to IRCTC, then the last leg from the station with a leave-by time (OSRM route), then the map. | "Maps are real. The long leg is the train: the right two stations, and straight into IRCTC. The last leg is routed live, from the station to the hospital door, with the time to leave." |
| S18 | Phone | `S18-near-you` | Near you: stay first (dharamshalas, cheapest bed first), then Jan Aushadhi before other pharmacies, and the labs nearby. | "Near the hospital it puts the cheapest bed first, a dharamshala before a hotel, and a Jan Aushadhi store before an ordinary pharmacy." |

### C9 · Money — 5:25–5:55
| Id | Front | Clip | Action | Narration |
|---|---|---|---|---|
| S19 | Phone | `S19-kharcha` | Kharcha tab: the journey estimate as a range with its published basis, the family's own limit, and entries to confirm. | "Every cost is an estimate with its source: railway fare slabs, state bus rates, meter tariffs. What the family tells us always wins. Their limit is theirs, and Saathi never spends past it without asking." |

### C10 · Scenario 1: a doctor goes on leave — 5:55–7:30
*(the end-to-end loop, recorded as one continuous take across all three screens)*

| Id | Front | Clip | Action | Narration |
|---|---|---|---|---|
| S20 | HMS | `S20-leave` | In OpenEMR, the oncologist is marked away all day on the take's day. Show the appointments unchanged. | "A doctor marks a day away, an ordinary save in the hospital's own calendar. The families' appointments don't change, so anything watching appointments sees nothing." |
| S21 | Console | `S21-asked` | Hospitals right now shows the leave. The questions sent appear per family and per language. | "Saathi sees it in seconds, works out which families it hits, and asks each one in their own language: which days can you travel, who's coming, what will it cost you." |
| S22 | Phone | `S22-question` | Phone: the question arrives. The family answers, by voice or text ("not before the 1st, two of us, about ₹1,400"). | *(the family's answer plays)* |
| S23 | Console | `S23-reading` | Approvals: the reading (not before …, 2 people, ₹ figure) sits beside the family's own sentence. The navigator agrees. | "An agent reads that into constraints, and a navigator checks the reading against the family's own words before the planner may act." |
| S24 | Console | `S24-plan` | Planner search: every date tried, the day the doctor is away *rejected* with its reason, and the offered day with its cost. | "The planner tries every date and keeps the refusals on the record. The doctor's leave day is ruled out. The new day comes with what it would cost the family." |
| S25 | Phone | `S25-proposal` | Phone: "Does 8 December suit you? About ₹1,400 for two." The family says yes. | "The day goes back to the family with its cost, and a question: does this suit you?" |
| S26 | Console → HMS | `S26-writeback` | The navigator approves. Cut to the OpenEMR calendar: the new appointment, written over FHIR. | "Only then does a person approve, and the booking is written into the hospital's own calendar." |
| S27 | Phone | `S27-confirmed` | Phone: confirmation, journey re-planned to the new date, read aloud in Hindi. | "And the family hears it in their language, with the journey already re-planned." |

### C11 · Scenario 2: one change, four different answers — 7:30–8:00
| Id | Front | Clip | Action | Narration |
|---|---|---|---|---|
| S28 | Console | `S28-four-answers` | Network board / Plan boards: Meera (dose moved 3 days the other way so the echo still fits), Josephine (held, because the report isn't back), Arun (25 km away, costs an afternoon), Priya (scan, bloods and review bundled into one trip). | "The same change means different things to different families. Meera's dose moves three days earlier so her heart scan still fits. Josephine's visit is held until her report is back. Arun lives close, so it costs him an afternoon. Priya's three separate trips become one." |

### C12 · Every step on the record — 8:00–8:25
| Id | Front | Clip | Action | Narration |
|---|---|---|---|---|
| S29 | Console | `S29-audit` | Audit log (hash chain intact) → the family's knowledge graph (each node tagged hospital / our records / the family's words) → reasoning log. | "Every step is on the record, hash-chained, including the refusals. And every fact says where it came from: the hospital, our records, or the family." |
| S30 | Console | `S30-research` | Research contribution: de-identified rows from consenting families only. | "With consent, the journey becomes evidence: why people stop coming, contributed without a name or an ID." |

### C13 · Close — 8:25–8:40
| Id | Front | Action | Narration |
|---|---|---|---|
| S31 | Illustration | Network diagram returns, then the logo and *"The hospital system runs the hospital. Saathi runs the journey between."* | "The hospital system runs the hospital. Saathi runs the patient's journey between hospitals, and it plugs into any of them." |

---

## Part 2 — Production steps after recording

| Id | Action |
|---|---|
| P1 | Trim each clip, mask anything sensitive (OpenEMR URL bar and admin name). |
| P2 | Generate the narration with Kokoro, one continuous take per step, voice `af_heart` (or `am_michael`), speed ~1.05. Check names via phonemes: Saathi, EKYATRA, OpenEMR, IRCTC, Jan Aushadhi, dharamshala, Kharcha, Beckn. |
| P3 | Remotion (`demo/film`): illustrations, front/back screen choreography, cross-fade and slide transitions, captions, music bed. Clip speed is fitted to the line, with no dead air. |
| P4 | Render, then sample frames against the narration. Make a ≤30 MB copy for phone. |

## Known gaps (decide before recording)

- **Negotiation agent**: not in the code. Either build it or leave it out of the film.
- **Welfare-fund checkbox** ("hospital covers the extra night"): only a single reference exists in the code, and it's not wired into approvals.
- **Bus**: priced in money rates (state transport per-km), but there's no bus partner flow.
- **Arrival clock** ("OPD running late"): needs an SSH tunnel Render can't hold, so it stays out of the hosted film, as `hosted-flow.mjs` already does.
- **Phone auto-refresh**: not yet watched unattended on a real device. Pull to refresh on camera if needed.
