# EKYATRA Saathi

**Readiness-driven visit planning that cuts wasted trips for families travelling for cancer care.**

> Health-a-thon 2026 · Cancer track · Patient / Caregiver
> Use case: Patient Follow-up & Continuity of Care

This is the initial boilerplate: a working decision core, a synthetic benchmark with
planted ground truth, and stubbed-but-typed integrations for the services the pilot needs.

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

## Architecture

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
                                           Claude — language layer only
                                                               │
                                        Bhashini ASR · NMT · TTS (hi, bn, or)
                                                               │
                                              WhatsApp · IVR ──┴──▶ the caregiver
```

### The one design decision that matters

**Claude never decides whether a family travels.** The go/wait decision is made by
`planner/tools.py::decide`, which is forty lines of deterministic code you can read in one
sitting. Claude's only job is to express a decision that has already been made, in Hindi,
Bengali or Odia.

The binding is structural, not just a prompt instruction:

1. The model is given the plan and the evidence claims, and nothing else. It has **no tools**,
   so there is nothing for it to fetch and nothing to leak.
2. Its response is constrained to a JSON schema whose fields map onto the plan's fields.
3. `language/guard.py::check_outbound` re-validates the rendered text against the plan
   afterwards — so a message that says "come on Thursday" under a `WAIT` plan is blocked
   even if layers 1 and 2 both failed.

Layer 3 is what protects the family. Layers 1 and 2 just make layer 3 fire rarely.

### Three models, and why each one

| Component | Technique | Why not something simpler |
|---|---|---|
| `graph/dependencies.py` | DAG over care steps | A review consult needs *both* reports. Blocking on direct parents only would send families in while radiology is still pending. |
| `readiness/conformal.py` | Split conformal prediction | A point estimate that is wrong by two days costs a 1,900 km round trip. Conformal gives a distribution-free coverage guarantee — and, crucially, **reports when it cannot give one**, which becomes `UNCERTAIN` rather than a confident guess. |
| `engagement/pelt.py` | PELT change-point detection | "No reply in 14 days" fires constantly for families who were always slow and misses the family who replied in an hour for six weeks and now takes four days. PELT detects a shift in *that family's own* baseline. |

---

## Quick start

No credentials and no services required — the prototype runs fully in-process on synthetic
patients with planted ground truth.

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

make demo     # the deck's journey, end to end, scored against ground truth
make test     # the decision core, the guard, and the scope boundary
make api      # http://localhost:8000/docs
```

Optional, once you have credentials — copy `.env.example` to `.env`:

```bash
ANTHROPIC_API_KEY=sk-...   # turns on the language layer; without it the planner
                           # still decides go/wait, it just does not write the message
```

### What `make demo` prints

For each synthetic family: what the hospital's default "come back in a week" would have
done, what Saathi decided, and why — followed by the benchmark:

```
  wasted trips, hospital default  ...
  wasted trips, with Saathi       ...
  wasted trips avoided            ...
  non-medical cost avoided        Rs ...
```

The baseline is the real-world practice of scheduling a return visit a fixed interval after
the procedure, with no reference to whether the reports will be ready.

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
  language/        Claude language layer, clinical guard, Bhashini ASR/NMT/TTS
  ingest/          ABDM / FHIR R4 reader, hospital turnaround feed
  channels/        WhatsApp Business API, Exotel IVR, console transport for local runs
  synthetic/       cohort generator with planted ground truth + the evaluation harness
  api/             FastAPI routes for the navigator console
console/           React navigator console (Vite + TypeScript)
tests/             decision core, guard, ledger, scope boundary
```

---

## Scope

Saathi is a logistics system. This boundary is enforced in code, not just documented.

**It never**
- Diagnoses or recommends treatment
- Reads or interprets report content — `ingest/abdm.py` drops `conclusion`, `presentedForm`
  and `result` before anything else sees the record, and `tests/test_abdm.py` asserts it
- Scores clinical risk
- Answers a clinical question — `guard.screen_inbound` routes it to the care team

**We measure**
- Wasted trips avoided
- Days the family spends in the city
- Non-medical out-of-pocket cost avoided (₹)
- Dropout after the first visit

---

## Status

Prototype. Synthetic patients with planted ground truth; the decision core, the guard and
the ledger are real and tested. The pilot adds live ABDM data and one hospital's status feed.

Integrations that are typed and wired but not yet exercised against a live endpoint: ABDM,
the hospital feed, Bhashini, WhatsApp and Exotel. Each turns on when its credentials appear
in the environment; see `.env.example`.

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
