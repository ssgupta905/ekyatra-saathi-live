# Everything EKYATRA Saathi actually does

Scanned from the code on 27 Nov 2026, not from memory. Each row says whether it
is **real** (wired, running, demonstrable on the deployed stack), **real but
unlit** (code exists and works, nothing in a UI reaches it), or **absent**.

The demo must only claim the first column.

---

## 1 · The hospital side (HMS)

| Capability | State | Where |
|---|---|---|
| Read appointments over FHIR R4 from **OpenEMR**, unmodified | real | `adapters/hospital/openemr.py`, `fhir.py` |
| SMART-on-FHIR backend services auth (`private_key_jwt`, RS384) | real | `adapters/hospital/_smart.py` |
| Read **provider leave** as an ordinary calendar event | real | `ports/hospital.py:AWAY_CODES` |
| Detect any appointment change by **snapshot diff** (no `dateChanged` in Bahmni, no usable `_lastUpdated` in OpenEMR) | real | `ports/hospital.py:AppointmentSnapshot.diff` |
| Write an approved booking **back** over the same FHIR API | real | `hospital_sync.rebook` |
| **Cannot cancel** — OpenEMR's FHIR Appointment has create, no update | honest limit | `openemr.py:supports_cancel = False` |
| Read arrival clock from OpenEMR's MariaDB (OPD running late) | real, **not on hosted stack** — needs an SSH tunnel Render cannot hold | `adapters/hospital/openemr_db.py` |
| Bahmni adapter | real but unlit | `adapters/hospital/bahmni.py` |
| Desk adapter (hospitals with no system at all) | real | `adapters/hospital/desk.py` |
| FHIR `Task` for "ask radiology" | real but unlit — OpenEMR does not surface Tasks in its UI | `_tasks.py` |

## 2 · The agents, and what governs them

| Capability | State | Where |
|---|---|---|
| Read a family's free-text reply into a **constraint** (Groq `gpt-oss-20b/120b`) | real | `live/actors.py:extract_request` |
| Strict JSON schema, every date re-validated, unknown step kinds dropped | real | `actors.py:REQUEST_SCHEMA` |
| **A person must agree with the reading** before the planner may act | real | `domain/requests.py:actionable` |
| Multi-turn conversation: propose → object → adjust → agree | real | `live/dialogue.py`, `runner.propose_to_family` |
| Plan search over dates, with **every rejection recorded and shown** | real | `planner/options.py`, `planner/search.py:Verdict` |
| Refuse a day the clinician is away | real | `options.py:days_away` |
| Conformal **readiness prediction** (will the report be back in time?) | real | `readiness/conformal.py` |
| Care rules per hospital (tolerance, sequencing, dose timing) | real | `planner/care_rules.py`, `domain/policy.py` |
| Treatment-touching options **structurally** require a doctor | real | `runner.approve_option` |
| Reasoning log — `EVENT CHECK INFER SEARCH PLAN GUARD HUMAN WRITE NOTIFY`, with real measured durations | real | `live/reasoning.py` |
| Knowledge graph per family | real | `live/knowledge.py` |
| Hash-chained **evidence ledger** | real | `ledger/evidence.py` |

## 3 · Language and the guard

| Capability | State | Where |
|---|---|---|
| Five languages: Hindi, Bengali, Odia, Tamil, English | real | `i18n`, `Translations.kt` |
| Questions **templated**, never generated — a model that writes the question can invent a premise | real | `language/questions.py` |
| Outbound guard: no clinical language, no false reassurance, no date it was not given | real | `language/guard.py` |
| Guard reads dates in **all five scripts**; unreadable date → diverted to a person | real | `guard.MONTH_NAMES` |
| Speech in (Sarvam `saarika:v2.5`, Groq Whisper) and out (`bulbul:v3`) | real | `adapters/speech/` |
| Service-voice check — the app verifies Sarvam played, not the phone's TTS | real | `MediaPlayerService` |
| Bhashini, Claude layers | real but unlit | `language/bhashini.py`, `claude.py` |

## 4 · Money

| Capability | State | Where |
|---|---|---|
| **Published rate table** — rail slabs, suburban rail, state bus, gazetted auto/taxi, lodging bands | real | `money/rates.json` |
| Every figure carries its **source and as-of date**, renders as an estimate | real | `money/rates.py` |
| Journey costing: cheapest realistic mode, both ways, a bed only if the trip needs one | real | `money/journey.py` |
| **A family's own stated figure beats ours**, and keeps the sentence they said it in | real | `runner.stated_fare_for` |
| No figure attributed to IRCTC / MakeMyTrip / OYO / Uber / Ola — they are booking hand-offs | real, enforced by test | `tests/test_money_rates.py` |
| Family budget conversation (what they can manage, per topic) | real | `domain/budget.py`, `orchestrator/budget.py` |
| Affordability tiers from their own papers | real | `domain/affordability.py` |
| **Kharcha** — the family's own books, spends tab | real | `live/kharcha.py`, `KharchaTab.kt` |
| Welfare fund for hospital-caused disruption | real | `api/live.py` hospital_caused |
| Razorpay / Cashfree payment adapters | real but unlit — no live keys | `adapters/payments/` |

## 5 · The network: who else is in it

| Capability | State | Where |
|---|---|---|
| Directory of hospitals, clinics, partners, desks | real | `domain/directory.py`, `api/directory.py` |
| Registry: resources (machines, staff, supply) per hospital | real | `domain/registry.py`, `api/registry.py` |
| Partner onboarding + partner web app | real | `api/onboarding.py`, `apps/partner-web` |
| **Beckn / ONDC** mobility — client, registry, signing, BPP | real but unlit — no live network | `adapters/beckn/` |
| IRCTC hand-off: real station codes, deep link, **never a train number or fare** | real | `domain/railways.py` |
| Uber / Ola / Rapido hand-off by deep link | real | `ui/Handoff.kt` |
| Pharmacy hand-off (PharmEasy, Tata 1mg) | real | `JourneySections.kt` |
| Jan Aushadhi before private pharmacy; dharamshala before hotel | real | `orchestrator/nearby_needs.py` |
| Nearby places: pharmacy, lab, clinic, equipment, **stay** | real | `api/nearby.py`, `domain/places.py` |

## 6 · Maps and routing

| Capability | State | Where |
|---|---|---|
| **OSRM** real driving routes, no key | real | `adapters/routes/osrm.py` |
| Google Routes adapter | real but unlit — needs billing | `adapters/routes/google.py` |
| Nominatim geocoding, cache-first | real | places adapters |
| Places from **OpenStreetMap** loaded into our own table | real | `tools/load_places.py`, `adapters/places/osm.py` |
| Google Places adapter | real | `adapters/places/google.py` |
| In-app map with route and hospital entrance | real | `ui/TripMap.kt` |
| Hospital entrances (which gate to use) | real | `domain/places.py` |
| Arrive-by derived **from the hospital's own booking** | real | `api/trip.py:arrive_by_source` |
| Intercity rail not routed — we hold no timetable licence | honest limit | `trip.py` note |

## 7 · The family's app

| Capability | State | Where |
|---|---|---|
| **Conversation is the default surface** | real | `FamilyViewModel.tab = MESSAGES` |
| Saathi proposes a date + cost and asks whether it suits | real | `runner.propose_to_family` |
| **Collapsed working inside the chat**, tapped open | real | `ThreadView.CostCard` |
| Each cost line says whose number it is, in the family's language | real | `costLabel()` |
| Record → transcribe → correct → send, by voice | real | `Composer.kt` |
| Read aloud in-language, with service-voice verification | real | `MediaPlayerService` |
| Plan, journey chain, near-you, spends | real | `PlanSections`, `NearYou`, `KharchaTab` |
| Auto-refresh: SSE + 20s poll + refresh on reconnect | real | `FamilyViewModel.keepUpToDate` |
| IVR and WhatsApp channels | real but unlit | `channels/` |

## 8 · The Console (control centre)

19 sections: Today, Families, Network board, Approvals, Hospitals right now,
Records, Reports, Research, Releases, Registries, Directory, Onboarding,
Operator, Configuration, Audit, Boards, Cohort, Issues, Story.

| Capability | State |
|---|---|
| **Disruption board** — one change, every family it hit, grouped by event | real (new) |
| Row expands to the agent trace + every date tried with its refusal | real |
| Request queue (readings awaiting a person) | real |
| Budget queue | real |
| Approvals with options, role-gated | real |
| Reasoning log, planner search, knowledge graph, evidence pane | real |
| Hospitals right now — what each system just changed | real |
| Research release with de-identification | real |
| Live SSE stream | real |

## 9 · Consent and research

| Capability | State |
|---|---|
| ABHA-keyed consent, per purpose, revocable, never a condition of care | real |
| Research release: no name, no ABHA, **no patient id even hashed** | real |
| District → state, distance → band, nothing clinical | real |
| Contributes to the gap nobody has data on: *why people stop coming* | real |

---

## Known broken / missing, as of this scan

1. **`packages/i18n/src/android.test.ts` fails** — `Translations.kt` has two
   authors; `make android-strings` deletes the hand-written half (`5d79b8d`).
   Fails identically before and after this branch. Needs a decision on which
   file is the source of truth.
2. **A leave never becomes a `Disruption`** — `_act_on_leave` asks and stops,
   so the board must group on the question instead of a disruption id.
3. **Slot contention is unhandled** — two approvals for the same slot would
   both succeed; the fastest reply wins by accident.
4. **No sanity check on a stated fare** — a family who says ₹1,400 for a 25 km
   trip is believed indefinitely.
5. **`make` Android targets broken on this machine** — `java_home -v 17` does
   not see the Homebrew JDK.
6. **Deleting an appointment is invisible** — `diff()` only walks what the
   hospital returns. Cancelling is caught; deleting is not.
