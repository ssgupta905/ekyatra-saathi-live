# EKYATRA Saathi

**Readiness-driven visit planning that cuts wasted trips for families travelling for cancer care.**

> Health-a-thon 2026 · Cancer track · Patient / Caregiver
> Use case: Patient Follow-up & Continuity of Care

A working decision core, a live simulation you can watch run, a navigator console that
shows its reasoning, and typed-but-unexercised integrations for the services a pilot needs.

---

## Start here

```bash
git clone <this repo> && cd ekyatra-saathi-live
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

make test     # 143 tests, no network, no credentials
make demo     # the whole cohort planned and scored against planted ground truth
```

Then, in two terminals:

```bash
make api      # :8000 — the world, paused until you press play
make console  # :5173 — the navigator console
```

Open <http://localhost:5173>, press ▶ in the header, and watch. Nothing is scripted:
every row in the activity strip is work that just ran, with the time it took.

**No credentials are needed for any of that.** Language rendering and the four actors turn
on when you add a key (see [Configuration](#configuration)); without one the clock still
ticks, the planner still decides, the guard still screens and the ledger still verifies.
That is the configuration CI runs and the one to fall back on if the venue's wifi fails.

### Contents

- [The problem](#the-problem) · [The rule](#the-rule)
- [How it fits together](#how-it-fits-together)
- [**Invariants — do not break these**](#invariants--do-not-break-these)
- [The live demo](#the-live-demo) · [The console](#the-console)
- [Layout](#layout) · [Configuration](#configuration)
- [Working on it](#working-on-it) · [Troubleshooting](#troubleshooting)
- [**Known gaps — where to pick up**](#known-gaps--where-to-pick-up)
- [Decisions already taken](#decisions-already-taken)

---

## The problem

Cancer care means a long journey, and the journey itself is ruinous.

| | |
|---|---|
| **60%** | of Tata Memorial Hospital's ~45,000 new patients a year come from outside Maharashtra [1] |
| **75%+** | of gastric and pancreatic cancer patients studied at Tata Memorial Centre travelled over 500 km [2] |
| **83%** | faced catastrophic non-medical costs — mean spend ₹88,433 on travel, lodging and food [2] |

Travel (43%) and accommodation (33%) make up most of that cost. Among patients travelling
over 500 km, 53% borrowed or sold assets to cope [2].

Every department optimises its own queue. Nobody counts the family's trips. The caregiver
holds the whole journey together alone, often in a language the hospital does not speak.

## The rule

> **Never travel for a step that is not ready.**

Saathi reads appointment and report *status* from ABDM and hospital feeds — never report
content — checks a dependency graph, and tells the caregiver in their own language whether
to come, what to bring, and where to go first. When a family goes quiet after a visit, a
navigator is alerted.

What is different: it optimises the family's trips and days away from home, not any
department's throughput.

---

## How it fits together

```
  ABDM / FHIR R4 ──┐
  Hospital feeds ──┼──▶  Dependency graph (Neo4j)  ──┐
  Caregiver replies┘     Readiness window (conformal)├──▶ Planner (LangGraph, typed tools)
                         Engagement monitor (PELT)  ─┘         │
                                                               │ decides: go / wait / uncertain
                                                               ▼
                                             Evidence ledger + clinical guard
                                                               │
                                                               ▼
                                      Groq / Claude — language layer only
                                                               │
                                        Bhashini ASR · NMT · TTS (hi, bn, or)
                                                               │
                                              WhatsApp · IVR ──┴──▶ the caregiver
```

### Three models, and why each one

| Component | Technique | Why not something simpler |
|---|---|---|
| `graph/dependencies.py` | DAG over care steps | A review consult needs *both* reports. Blocking on direct parents only would send families in while radiology is still pending. |
| `readiness/conformal.py` | Split conformal prediction | A point estimate that is wrong by two days costs a 1,900 km round trip. Conformal gives a distribution-free coverage guarantee — and, crucially, **reports when it cannot give one**, which becomes `UNCERTAIN` rather than a confident guess. |
| `engagement/pelt.py` | PELT change-point detection | "No reply in 14 days" fires constantly for families who were always slow and misses the family who replied in an hour for six weeks and now takes four days. PELT detects a shift in *that family's own* baseline. |

---

## Invariants — do not break these

Everything else in this codebase is negotiable. These are not. Each is enforced in code and
guarded by a named test, so if you break one you will find out.

### 1. The model never decides whether a family travels

The go/wait decision is `planner/tools.py::decide` — about forty lines of deterministic code
you can read in one sitting. Every edge in the LangGraph state machine (`planner/graph.py`)
is chosen by code; the model is called in exactly one node, `compose`, and cannot influence
routing. An agent that could choose its own path could choose to tell a family to travel.

The binding is structural, not a prompt instruction:

1. The model gets the plan and the evidence claims, and nothing else. It has **no tools**,
   so there is nothing to fetch and nothing to leak.
2. The response is constrained to a JSON schema whose fields map onto the plan's fields.
3. `language/guard.py::check_outbound` re-validates the rendered text against the plan
   afterwards — so a message saying "come on Thursday" under a `WAIT` plan is blocked even
   if layers 1 and 2 both failed.

Layer 3 is what protects the family. Layers 1 and 2 just make layer 3 fire rarely.
*Guarded by* `test_language_layer.py`, `test_groq_layer.py`, `test_guard.py`.

### 2. Every backend is bound identically

`language/rendering.py` owns the system prompt, the response schema, the cross-checks and
the guard call. `claude.py` and `groq_layer.py` contribute **only** how to reach their API.
The moment the two diverge is the moment the weaker one becomes the way in — so if you add
a third backend, it imports from `rendering.py` and adds nothing of its own.
*Guarded by* `test_groq_layer.py::test_both_backends_are_bound_by_the_same_schema_and_prompt`,
which asserts they share the same Python objects.

### 3. An actor may produce an input or a reading, never a decision

The four Groq actors (`live/actors.py`) write the ward note a hospital would write, the
message a caregiver would send, a summary of records a navigator already has, or an existing
sentence in another language. None decides anything, bounds a readiness window, or ranks an
alert. That is why being wrong is cheap everywhere in that file, and why every method returns
`None` on failure rather than raising into the tick loop.
*Guarded by* `test_actors.py`.

### 4. Nothing reaches a family without a source

Every sentence traces to a ledger row. `ledger/evidence.py` is append-only and hash-chained,
so altering an entry invalidates every entry after it. `check_outbound` refuses a message
carrying no evidence refs, or refs that do not resolve.
*Guarded by* `test_ledger.py`, `test_guard.py`.

### 5. The ledger grows only when a fact changes

`record_once`, not `record`. Planning is idempotent; the live runner re-plans every patient
every simulated day, and without this the one row that matters is buried under hundreds of
identical copies and an auditor learns nothing from the chain.
*Guarded by* `test_ledger.py::test_record_once_does_not_restate_an_unchanged_fact`.

### 6. Report content never enters the system

`ingest/abdm.py` drops `conclusion`, `presentedForm` and `result` before anything else sees
a record. No model in `domain/models.py` has a field that could hold report content.
*Guarded by* `test_abdm.py`.

### 7. Alerts carry signals, never scores

There is no ranking number in the interface and no field in the data model to hold one.
Navigators see what changed and decide. The deliberate absence is the design.

### 8. The console reflects the world; it must not cause it

`POST /api/plan` reads the runner's latest real planning run. A navigator opening a family
must not be the reason its ledger grows. `?recompute=true` exists for tests and scripted runs.
*Guarded by* `test_live_api.py::test_reading_a_plan_does_not_grow_the_ledger`.

### 9. The test suite runs with no credentials, ever

`tests/conftest.py` blanks `GROQ_API_KEY` and `ANTHROPIC_API_KEY` before any `Settings` is
built, and asserts the suite is credential-free. Without it, the moment someone puts a real
key in `.env` the tests quietly start making network calls — slow, flaky, and no longer a
test of the thing they claim to test.

---

## The live demo

`make api` boots a world rather than a snapshot. A simulation clock runs the cohort forward
a day at a time, and **every process a viewer sees is an actual run** — nothing is scripted,
replayed or animated.

Press play and this happens on its own:

1. the clock advances a simulated day;
2. a report whose planted ready-date has passed becomes a **desk candidate** — a free-text
   ward note plus the record it implies, waiting for a human;
3. someone confirms it (or it auto-confirms after two days, and the event says so), which is
   the only thing that changes a step;
4. the real LangGraph planner re-runs over all fifty families;
5. the family whose prerequisite just landed flips WAIT → GO, the outstanding node
   disappears from its trace, and a message is rendered and guarded;
6. the ledger gains **one** row — the fact that changed — and re-verifies;
7. the cohort is rescored against planted ground truth.

The activity strip carries the measured wall-clock cost of each: `planner re-ran 50
families · 62 ms` is a timing taken around the call, not a number chosen to look plausible.
That card is what makes the rest of the console checkable rather than merely plausible.

Two things an operator can do, and both are *inputs* rather than decisions: confirm a desk
record, and put a message in a family's mouth. What follows happens because the system
reacted.

Ground truth is read in exactly one place — `live/world.py::due_releases`, deciding when the
lab has finished — and never reaches the planner, which still has to bound the wait from the
conformal model like it would in a hospital.

```bash
make api                          # :8000, paused until you press play
make console                      # :5173
SAATHI_LIVE_AUTOSTART=true        # start the clock on boot instead
SAATHI_LIVE_SECONDS_PER_DAY=2     # default 4
```

### Running it on stage

- **Reset first.** The Reset button in the Cohort view, or
  `POST /api/live/control {"action":"reset"}`. Same seed, same cohort, every time —
  rehearsable.
- **Step, don't play, while you are talking.** The ⏭ button advances exactly one day, so you
  can narrate what changes.
- **The desk queue is the beat.** Confirm a record by hand and the whole chain fires in front
  of the audience: ledger row, step released, planner re-run, decision flips, message
  rendered and guarded.
- **Inject a clinical question** from the Cohort view to show the guard holding it with the
  actual trigger words.
- **If the wifi dies**, take the key out of `.env` and restart. Everything except the message
  text still works, and the console says the language layer is off.

### Groq, and the four actors

The live demo's language backend is Groq: `openai/gpt-oss-20b` does constrained-decoding
structured output fast enough that a family's message lands inside a simulated day rather
than after it (measured: 1.1–1.7 s for a Bengali message). Set `GROQ_API_KEY` in `.env` and
it is preferred over Claude automatically.

With the key set, four actors also run:

| Actor | Produces | What stops it being believed |
|---|---|---|
| Caregiver | A real WhatsApp message in the family's language | The real `screen_inbound` reads it; a clinical question is logged, never answered |
| Desk clerk | The ward note, and the record parsed back out of it | A parse naming an unknown step is rejected; a human confirms the rest |
| Call brief | Four lines before a navigator dials | A line whose ledger citations do not resolve is dropped before display |
| Narration | The on-screen trace in the family's language | Each line passes `check_outbound` against the same plan; a failure shows as held |

Cost control: only the ~8 **watched** families get messages rendered and actors run; all
fifty are planned every day for scoring. A message is re-rendered only when something the
wording depends on moves — decision, travel date, blockers, checklist. Counters are in
`GET /api/live`, so an overrun is visible rather than silent.

---

## The console

One light theme — an Apple-web palette on a `#f5f5f7` plane — and one organising idea:
**the decision is never shown without the chain that produced it.**

- **Why this decision** replays the plan as a chain of claims — target step, prerequisite
  gate, each outstanding prerequisite with its calibrated interval, then the verdict with the
  rule it was reached under, quoted rather than paraphrased. Every link names its basis, and
  a basis that is a ledger entry is clickable: it jumps to that row and flashes it.
- **Readiness windows are drawn as intervals**, never as dates, with the coverage level and
  the calibration count beside them. An uncalibrated window draws no bar at all and says why.
- **The message pipeline** shows all four gates — plan, render, guard, send — even when they
  all pass, because the useful fact is which one *would* have stopped it.
- **The activity strip** is the live log, each row carrying the measured cost of the work
  behind it.
- **The desk queue** shows the ward note, the record parsed from it, and a confirm button —
  because a report finishing in the lab and a hospital system knowing about it are two
  different events.
- **Alerts carry signals, not scores.**

Colour is load-bearing in exactly three places (status, the single data hue, ink) and never
carries meaning alone — every status wears a glyph and a word. Status steps are Apple's
accessible system colours, contrast-checked against both surfaces; the blue ramp is validated
as an ordinal ramp.

---

## Layout

```
backend/saathi/
  domain/          closed vocabularies and frozen models — no field can hold report content
  graph/           dependency DAG; in-memory reference + Neo4j implementation + schema.cypher
  readiness/       split conformal predictor over per-queue turnaround history
  engagement/      PELT change-point detector for disengagement
  planner/         typed tools + the LangGraph state machine (every edge decided by code)
  ledger/          hash-chained append-only evidence ledger
  language/        rendering.py (the shared binding) + groq_layer.py + claude.py,
                   clinical guard, Bhashini ASR/NMT/TTS
  ingest/          ABDM / FHIR R4 reader, hospital turnaround feed
  channels/        WhatsApp Business API, Exotel IVR
  synthetic/       cohort generator with planted ground truth + the evaluation harness
  live/            clock, mutable world, event bus, the tick runner, the Groq actors
  api/             FastAPI routes for the console, plus the live stream and controls
console/
  src/lib/         typed API client, display vocabulary, the explanation model, SSE client
  src/ui/          design tokens in styles.css, glyphs, shared primitives
  src/components/  decision hero, trace, readiness interval, pipeline, desk queue, ledger
tests/             decision core, guard, ledger, scope boundary, the live world, the actors
```

**Where to add things**

| If you are adding… | Put it in | And |
|---|---|---|
| a new rule about when to travel | `planner/tools.py` | add a case to `test_planner.py`; the graph should not need to change |
| a new care-step type | `domain/enums.py`, then `graph/dependencies.py` edges | enums are closed on purpose — a typo becomes an import error |
| a new language backend | `language/<name>_layer.py` | import everything from `rendering.py`; add a twin of `test_groq_layer.py` |
| a new actor | `live/actors.py` | it may produce an input or a reading, never a decision; return `None` on failure |
| a new card in the console | `console/src/components/` | use `Card` from `ui/primitives.tsx` and tokens from `styles.css`; no new colours |
| a new event the console reacts to | `live/events.py::EventKind`, published from `runner.py` | add it to `ALL_KINDS` and the tone/label maps in `console/src/lib/live.ts` |

---

## Configuration

Copy `.env.example` to `.env`. Everything is optional; each integration turns on when its
credentials appear.

| Variable | Default | What it does |
|---|---|---|
| `GROQ_API_KEY` | — | Turns on the language layer **and** the four actors. Preferred over Claude. |
| `SAATHI_GROQ_MODEL` | `openai/gpt-oss-20b` | Must support `strict: true` structured outputs. |
| `SAATHI_GROQ_ACTOR_MODEL` | `openai/gpt-oss-120b` | Actors write prose, so they get more room. |
| `ANTHROPIC_API_KEY` | — | Fallback language layer. Does not enable actors. |
| `SAATHI_LIVE_SECONDS_PER_DAY` | `4.0` | Real seconds per simulated day. |
| `SAATHI_LIVE_WATCHED` | `8` | Families that get messages rendered and actors run. |
| `SAATHI_LIVE_AUTO_CONFIRM_TICKS` | `2` | Days a desk candidate waits before it self-confirms. |
| `SAATHI_LIVE_INBOUND_EVERY_SECONDS` | `15` | How often the caregiver actor writes in. |
| `SAATHI_LIVE_START_OFFSET_DAYS` | `3` | Days to rewind at boot, so reports land while someone is watching. |
| `SAATHI_LIVE_AUTOSTART` | `false` | Start the clock on boot. |
| `SAATHI_CONFORMAL_ALPHA` | `0.1` | 1 − α is the coverage guarantee on readiness windows. |

`.env` is gitignored. **Never commit a key.** `.env.example` is the file that gets committed,
and it holds names only.

---

## Working on it

```bash
make test                                                # the whole suite, ~20s
.venv/bin/python -m pytest tests/test_live_world.py -q    # one file
.venv/bin/python -m pytest -q -k "guard"                  # one topic
make lint                                                # see the note below
cd console && npm run build                              # strict TypeScript + Vite
```

**Conventions worth matching**

- Tests are named as sentences that state the claim: `test_a_report_does_not_release_itself`.
  A reviewer should be able to read the test names and learn the rules.
- Comments explain *why*, not *what*. Modules carry their reasoning in the docstring.
- Enums are closed. Anything crossing a module boundary is one of them.
- New behaviour that protects a family gets a test that fails without it. A test that cannot
  fail is documentation wearing a test's clothes.

**`make lint` fails on a clean checkout, and always has.** It runs `ruff check` *and*
`ruff format --check`, and the format half has never passed — 24 files would be reformatted
at the initial commit, before any of this work. CI only runs `ruff check`, which is the real
signal. Don't run `ruff format` across the repo to make it green: it rewrites two dozen
untouched files and buries whatever diff you are actually working on. Fix it as its own
dedicated commit if you want it fixed.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'saathi'` | `.pth` files are not processed in some venvs, so the editable install's path never reaches `sys.path` | The Makefile already sets `PYTHONPATH=backend` for `api` and `demo`. Prefix ad-hoc commands the same way. |
| `ERROR: [Errno 48] Address already in use` | A previous `make api` is still running | `lsof -ti:8000 \| xargs kill -9` |
| Console shows "stream down" | The API is not running, or it restarted | The SSE client reconnects on its own every 2s; check `make api` is up. |
| Tests hang or slow down after adding a key | Something bypassed `tests/conftest.py` and is making real API calls | Nothing in the suite should need a key — find the call and stub it. |
| The world runs but nothing changes | Every report has already been released | Reset, from the Cohort view or `POST /api/live/control {"action":"reset"}`. |
| `make demo` numbers differ from this README | The cohort is seeded (`seed=20260925`); changing the generator changes the numbers | Intentional changes are fine — update the numbers here too. |

---

## Known gaps — where to pick up

Ordered by how much it matters. Each is real and reproducible today.

### 1. The inbound clinical guard is Latin-script only · **safety**

`guard.CLINICAL_TERMS` is entirely Latin script, so a clinical question written in
Devanagari, Bengali or Odia is **answered rather than routed to a person**. The same
question, four ways:

```
blocked  "what does the report say, is it cancer?"     triggers: ['what does the report']
blocked  "report mein kya aaya, cancer hai kya?"       triggers: ['cancer hai']
PASSED   "रिपोर्ट में क्या आया, क्या यह कैंसर है?"
PASSED   "এই রিপোর্টে ক্যান্সার আছে কি?"
PASSED   "disease ka kya matlab hai"
```

This was deliberately **not** fixed here: deciding which words count as clinical in three
languages is a clinician's call, and being wrong in either direction is costly —
over-blocking buries navigators, under-blocking is what you have now. The outbound direction
has already been fixed the same way, and is the pattern to copy: see `guard.MONTH_NAMES` and
`guard.stated_dates`, which read Indic numerals and month names and fail closed on anything
unreadable.

**Next step:** get the vocabulary from your clinical partner, extend `CLINICAL_TERMS` per
language, and add a twin of `test_a_wrong_date_is_blocked_in_every_pilot_language`.

### 2. Ward notes read machine-shaped · demo quality

The desk-clerk actor is handed the internal step id and parrots it, so notes come out as
`"P0003-pathology_report released 2026-10-02"` rather than something a clerk would type.
Give it the patient reference and report type instead, and let the parser resolve the id from
that patient's open records — which also makes the parse a real resolution rather than a
copy, and makes the "reject unknown step id" guard meaningful.
Files: `live/actors.py::WARD_NOTE_SYSTEM`, `PARSE_SYSTEM`.

### 3. A GO plan's travel date slides every day · modelling

`tools.earliest_safe_travel_date` recomputes from the current day, so a family already told
"travel on the 5th" is told "the 6th" tomorrow. The message is re-rendered correctly each
time, so nothing is inconsistent — but in reality a communicated GO is a commitment. Decide
whether a plan should pin its date once issued.

### 4. Nothing is persisted

The world, the ledger and the plans all live in process; restarting `make api` starts over.
`db/tables.py` and `db/session.py` are written and unused. For a pilot, the ledger is the one
that has to survive a restart.

### 5. Voice is stubbed

Groq's TTS covers English and Arabic only, so Hindi/Bengali/Odia speech stays with Bhashini
(`language/bhashini.py`, typed, needs `SAATHI_BHASHINI_*`). Groq's Whisper **is**
multilingual, so a live mic → transcribe → guard leg is reachable without Bhashini if you
want the inbound half first.

### 6. Integrations are typed but never exercised against a live endpoint

ABDM, the hospital feed, WhatsApp and Exotel. Each turns on when its credentials appear.
ABDM is deliberately last — it is an upgrade, not a prerequisite.

### 7. Narrow-viewport layout is unverified

The console collapses its rail below 900px in CSS, but that has not been seen rendered. It is
a desktop console, so this is low priority.

---

## Decisions already taken

Written down so nobody re-litigates them from scratch. Reverse any of them deliberately, not
by accident.

| Decision | Why |
|---|---|
| Groq is preferred over Claude when both keys are present | The live demo needs sub-second rendering; `gpt-oss-20b` does constrained decoding at roughly 1000 tok/s. Claude stays the quality fallback. |
| SSE, not WebSockets | The stream is one-way server→client. No extra dependency, works through the Vite proxy, reconnects for free. |
| A report release goes through a desk queue | A report finishing in the lab and a hospital system knowing about it are different events. Conflating them is how software ends up believing things nobody told it. |
| The planner is re-run, not patched, on every change | 50 families in ~65 ms. Incremental invalidation would be faster and far easier to get subtly wrong. |
| `record_once` instead of `record` | See invariant 5. |
| The console goes live in place rather than gaining a demo-only screen | Judges should watch the screens a navigator actually uses. |
| Text only; no voice leg yet | Groq has no Indian-language TTS, and a half-real voice demo is worse than none. |
| Light theme only | A navigator should never see two different renderings of the same decision. |

---

## Scope

Saathi is a logistics system. This boundary is enforced in code, not just documented.

**It never**
- Diagnoses or recommends treatment
- Reads or interprets report content — `ingest/abdm.py` drops `conclusion`, `presentedForm`
  and `result` before anything else sees the record, and `tests/test_abdm.py` asserts it
- Scores clinical risk
- Answers a clinical question — `guard.screen_inbound` routes it to the care team, with the
  gap in [Known gaps](#known-gaps--where-to-pick-up) §1

**We measure**
- Wasted trips avoided
- Days the family spends in the city
- Non-medical out-of-pocket cost avoided (₹)
- Dropout after the first visit

---

## Status

Prototype. Synthetic patients with planted ground truth; the decision core, the guard, the
ledger and the live world are real and tested — 143 tests, no network. The pilot adds live
ABDM data, one hospital's status feed, and persistence.

Before any real-patient pilot: the partner hospital's ethics and data-protection review, and
a clinician's sign-off on the guard vocabulary.

---

## Sources

1. C.S. Pramesh, Director, Tata Memorial Hospital, in *Think Global Health*, Oct 2022
2. IIPS and Tata Memorial Centre, *Journal of Cancer Policy*, 2025
3. CROCODILE study group, *The Lancet Regional Health: Southeast Asia*, 2022 — 90% of
   colorectal cancer patients across five tertiary hospitals faced catastrophic spending;
   9.4% had an unplanned treatment interruption

The pitch deck is in [`docs/EKYATRA-Saathi-deck.pdf`](docs/EKYATRA-Saathi-deck.pdf).

## License

MIT — see [LICENSE](LICENSE).
