# Grounding Saathi on real data: ABDM + ICMR-NCDIR feasibility brief

Internal working document. Companion to [`docs/src/solution-note.html`](src/solution-note.html)
(the pitch-facing piece) — this one is for the team deciding what to actually do next.

## 1. Why now

Saathi runs today entirely on a synthetic cohort (`backend/saathi/synthetic/generate.py` →
`backend/saathi/live/world.py`). The README already names the next step without spelling out
how to take it:

> "ABDM, the hospital feed, WhatsApp and Exotel. Each turns on when its credentials appear.
> ABDM is deliberately last — it is an upgrade, not a prerequisite."
> — [`README.md:511-514`](../README.md#L511)

> "Prototype. Synthetic patients with planted ground truth... The pilot adds live ABDM data,
> one hospital's status feed, and persistence. Before any real-patient pilot: the partner
> hospital's ethics and data-protection review, and a clinician's sign-off on the guard
> vocabulary." — [`README.md:563-568`](../README.md#L563)

This brief turns that into an actual plan: two institutional tracks (NHA/ABDM and
ICMR-NCDIR), mapped against what the codebase can already do versus what's missing.

## 2. Two-track strategy

### Track A — NHA / ABDM (self-serve, start immediately)

ABDM (Ayushman Bharat Digital Mission) is the closest existing national framework to what
Saathi needs: ABHA identifiers plus consent-based exchange of digital health records between
participating providers. Unlike NCDIR, there is a public, self-serve path that doesn't require
a partnership to begin:

1. Apply for ABDM Sandbox access at the official sandbox site, supplying product description,
   API documentation, technical contact, and organizational details.
2. Receive sandbox client ID/secret; register Saathi's role. Saathi **reads** records rather
   than holding them, so the natural role is **HIU** (Health Information User) — a HIP
   (Health Information Provider) is a system that *creates and holds* records (e.g. a hospital
   LIS), which Saathi is not.
3. Integrate in milestones: **M1** (ABHA creation/linking — create and verify ABHA numbers via
   OTP/QR, link patient identity), **M2** (HIP services), **M3** (HIU services — request/view
   records with consent). Saathi's use case sits mainly in M1 + M3.
4. Production access requires certification by an NHA-empaneled compliance auditor — a later
   step, not a blocker to starting sandbox integration now.

*(Sources are vendor guides and the ABDM developer forum, not the primary ABDM documentation —
re-verify the exact URL and current steps at `sandbox.abdm.gov.in` before registering; one
source used `sandbox.ndhm.gov.in`, the project's former name, so confirm which is current.)*

### Track B — ICMR-NCDIR / NCRP (needs a hospital partner + a defined study)

NCDIR coordinates the National Cancer Registry Programme (NCRP): a network of roughly 236
hospital-based (HBCR) and 36 population-based cancer registries, each submitting data on a
standardized common-core form, with NCDIR acting as **custodian** of that data under an
ethics-committee-reviewed sharing policy. Unlike ABDM, there is no evidence of a public
self-serve application path — onboarding runs through registered hospitals submitting their own
data, not external systems querying in. This matches the user's own framing exactly: *NCDIR
becomes relevant once there's a hospital partner and a clearly defined validation study* — not
before. The near-term move on this track is not a registration form, it's identifying that
partner and that study design.

### Where the tracks intersect

The ideal pilot partner is a hospital that is **both** ABDM-facility-registered and an
NCRP-registered HBCR. That single partner would let Saathi validate against the live-status
layer (ABDM: is the report ready, is the appointment scheduled) and the oncology-specific
outcome data (NCDIR: what actually happened to the patient) at the same time, with one ethics
review covering both.

## 3. Technical readiness map

Two rounds of codebase exploration found real, tested scaffolding for exactly this purpose,
already written and then left disconnected — this is the strongest argument that the gap here
is wiring, not a from-scratch build:

| Piece | File(s) | State |
|---|---|---|
| FHIR → domain projection | `backend/saathi/ingest/abdm.py` | Real `ABDMClient` (httpx-based), `to_care_step()` projector from FHIR `DiagnosticReport`/`Appointment` into Saathi's `CareStep`. The content-redaction boundary (drop `conclusion`/`presentedForm`/`result`) is enforced and asserted by `tests/test_abdm.py` — also called out in the solution note (`docs/src/solution-note.html:209`). **No OAuth/client-credentials token exchange implemented. Never instantiated anywhere in the running app.** |
| Consent model | `backend/saathi/domain/consent.py`, `backend/saathi/consent/registry.py` | A full ABDM-consent-artifact-shaped model: `ConsentRequest`/`ConsentGrant`/`AccessAttempt`, DPDP capacity types (`SELF`/`NOMINEE`/`GUARDIAN`), purpose limitation, 90-day default grant, hash-chained access log via the existing evidence ledger. Tested in `tests/test_consent.py`. The solution note already claims this behavior publicly (`docs/src/solution-note.html:223-224`: "Consent is enforced at the point of reading, and refusals are logged... follows the DPDP Act 2023 and ABDM consent artefacts") — **but it is not wired into `api/deps.py::AppState` or any API route, and the main README never mentions it.** |
| Persistence | `backend/saathi/db/tables.py`, `backend/saathi/db/session.py` | SQLAlchemy schema mirroring every domain model 1:1, explicitly commented as "what the pilot writes to." **No Alembic migrations yet (`create_all` only). Nothing in the running app calls into it today** — everything is in-memory. |
| Hospital turnaround feed | `backend/saathi/ingest/hospital_feed.py` | CSV parser + client for turnaround-time history, feeding the conformal-prediction readiness model. **Unused** — a separate, thinner, ad hoc `httpx.get` in `tools/hospital.py` is the only thing actually wired to `SAATHI_HOSPITAL_FEED_URL` today, and it does resource-status lookups only, not turnaround history. |
| Patient identity | `backend/saathi/domain/models.py::Patient` | No `abha_number` field yet. But the consent layer and `ABDMClient.care_steps(abha_id, patient_id)` already treat `abha_number`/`abha_id` as a key *separate* from Saathi's internal `patient_id` — the convention is established, just not threaded onto `Patient` itself. |
| Communication channels | `backend/saathi/channels/whatsapp.py`, `backend/saathi/channels/ivr.py` | Real WhatsApp Graph API and Exotel IVR clients, each gated behind a `*_enabled` settings flag. Never instantiated — the live runner simulates delivery via an in-memory outbound list. |

Also worth noting: `config.py` gives every other optional integration (Neo4j, WhatsApp,
Bhashini) a computed `*_enabled` property derived from its credentials — **ABDM and the
hospital feed are the only two integrations without one.** `SAATHI_ABDM_BASE_URL`,
`SAATHI_ABDM_CLIENT_ID`, and `SAATHI_ABDM_CLIENT_SECRET` are declared in `Settings` and in
`.env.example` but read by nothing else in the codebase today.

## 4. Nearest technical step: wire the consent layer first

Per direction to include this now rather than defer it: the consent architecture should land
**ahead of** any live data pull, not after. ABDM's entire value proposition is consent-gated
exchange — pulling sandbox FHIR data without first wiring `ConsentRegistry` would mean the demo
doesn't actually reflect how real data is allowed to flow, and the solution note's public claim
about consent-gated reads would still be untested in practice.

Concrete follow-on coding tasks this implies (scoped for a later, separate engineering pass —
not part of this brief):

- Add `abha_number: str | None` to `Patient` and `FamilyMember` in `domain/models.py`.
- Instantiate `ConsentRegistry` inside `api/deps.py::AppState`; add `/consent/*` routes
  (request / grant / revoke / resolve / access-log) so consent state is visible and testable
  through the API, not just in unit tests.
- Build the missing ABDM OAuth client-credentials token exchange and plug it into
  `ABDMClient.__init__` (currently takes a raw token with no acquisition flow).
- Add a `settings.abdm_enabled` property to `config.py`, mirroring `whatsapp_enabled` /
  `neo4j_enabled`, and gate `ABDMClient` instantiation behind it.
- Wire `ConsentRegistry.resolve()` as the gate in front of every `ABDMClient.care_steps()` call,
  so a sandbox pull with no active grant produces a logged refusal, not data.

## 5. Phased roadmap

- **Phase 0 — now, no external approval needed.** Register for the ABDM Sandbox. Draft the
  NCDIR outreach note. Identify 1–2 candidate partner hospitals that are plausibly both
  ABDM-facility-registered and NCRP HBCR-registered.
- **Phase 1 — engineering, sandbox-only.** Consent-layer wiring (§4) + ABHA field + OAuth token
  exchange. Validate `ABDMClient.care_steps()` end-to-end against ABDM sandbox test ABHA IDs —
  entirely synthetic-but-real-protocol data, no real patient involved yet.
- **Phase 2 — institutional outreach.** Formal technical/policy alignment conversation with NHA
  (by this point largely evidenced by working sandbox integration). In parallel, direct inquiry
  to NCDIR once a candidate hospital partner and a validation-study design exist.
- **Phase 3 — pilot.** Partner hospital's ethics and data-protection review, clinician sign-off
  on the guard vocabulary (both already named as prerequisites in `README.md:567-568`), then a
  scoped real-data pilot against that one hospital.

## 6. Open questions / risks

- DPDP Act 2023 compliance posture beyond what `domain/consent.py` already models — has this
  been reviewed by anyone with actual DPDP expertise, or just designed against the public spec?
- Data residency and retention for any persisted real records — `db/` has no migrations yet,
  and no retention/deletion policy has been designed.
- Does NCRP data sharing for Saathi's use case require its own Institutional Ethics Committee
  (IEC) review distinct from the partner hospital's own registry participation?
- ABDM sandbox URL and process details above came from vendor blogs and the developer forum,
  not NHA's own documentation — confirm against the live sandbox site before registering
  anything.
- NCDIR/NCRP shows no public API or self-serve onboarding in available sources — worth directly
  asking NCDIR whether one exists before assuming the manual/common-core-form path is the only
  option.

## 7. Phase 0 follow-through (2026-10-22)

Drafted and researched so far:

- **ABDM Sandbox eligibility, re-checked:** individuals *can* apply (an ABDM developer-forum
  user confirms signing up under the "Individual" category), not just registered
  organizations — approval isn't automatic though, and vague applications have been rejected
  with a request to "re-apply with more specific intention." Worth writing a specific, concrete
  intent statement in the application rather than a generic one. Still unverified against
  official docs — re-check at `sandbox.abdm.gov.in` directly before applying.
- **Candidate partner hospital — Tata Memorial Hospital (Mumbai).** Already the uncredited
  inspiration behind this codebase's synthetic `hospital_id="TMH-MUM"` and the README's cited
  patient-travel statistics. Web research confirms it independently: TMH is NCRP's **largest
  single HBCR contributor** (81,260 of 667,666 total cases across 58 HBCRs in the 2012–2016
  NCRP report — the single biggest registry in the network), so it is already deeply engaged
  with NCDIR. Its ABDM/ABHA integration status (Health Facility Registry listing) was **not**
  confirmed by web search — check the official ABDM Health Facility Registry directory, or ask
  the hospital's digital-health/IT team directly, before assuming either way.
- **No public combined ABDM+NCRP hospital list exists** to search against — ABDM facility
  status lives in the Health Facility Registry (HFR) on the ABDM portal; the NCRP hospital
  roster lives in NCDIR's own annual reports (279 cancer-treating hospitals + 44 regional/
  tertiary centres per the 2026 annual report) and the ICMR open-data portal. Cross-referencing
  the two is a manual lookup, not a searchable join — Tata Memorial is a strong enough lead on
  its own that this may not be necessary before a first approach.
- **Outreach note to NCDIR drafted:** [`docs/outreach/ncdir-outreach-note.md`](outreach/ncdir-outreach-note.md) —
  written as a cold, pre-partnership inquiry under Ankshuk Ray's name as an independent/
  hackathon project. Flagged internally as possibly better routed through a specific hospital's
  own registry/research office once one is engaged, rather than sent cold to NCDIR itself —
  see the note's own "notes for whoever sends this" section.
- **Consent-layer wiring scoped as a standalone ticket:** [`docs/tickets/consent-layer-wiring.md`](tickets/consent-layer-wiring.md) —
  concrete file-level changes, explicitly out-of-scope items, and a verification checklist, kept
  separate from this brief so it can move into an actual tracker without carrying the rest of
  the brief's context with it.

## 8. Immediate next actions

| Action | Owner | Status |
|---|---|---|
| Submit ABDM Sandbox application (individual category, specific intent statement) | You (account creation isn't something I'll do on your behalf) | Not started — drafting the application's written content is doable on request |
| Confirm current sandbox URL/HIU steps directly against `sandbox.abdm.gov.in` | Either | Partially done via web search; needs a direct check of the live site |
| Review and send (or redirect) the NCDIR outreach note | You | Drafted, not sent |
| Decide whether to approach Tata Memorial Hospital directly instead of/before NCDIR | You | Open question — see §7 |
| Move the consent-layer ticket into an actual tracker and start the work | Engineering | Scoped, not started |
