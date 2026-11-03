# Ticket: wire ConsentRegistry into the running app

> **Status: done except item 4.** Items 1, 2, 3 and 5 are in (`Patient.abha_number` and
> `settings.abdm_enabled` already existed; the registry is built in `Container`; routes are in
> `api/consent.py`, keyed by patient rather than ABHA number so caregiver access is checked on the
> path). Consent state now persists in the real world (migration `0007`). Item 4, gating
> `ABDMClient` reads through `resolve()`, waits on the ABDM OAuth ticket.

Scoped engineering ticket, not yet filed as a GitHub issue — copy into the tracker of choice
when ready. Written to stand on its own (an engineer picking this up needs no other context).

## Why

`backend/saathi/domain/consent.py` and `backend/saathi/consent/registry.py` already implement
a full ABDM-consent-artifact-shaped model — `ConsentRequest`/`ConsentGrant`/`AccessAttempt`,
DPDP capacity types, purpose limitation, a 90-day default grant, and a hash-chained access log
written through the existing evidence ledger. It is tested (`tests/test_consent.py`) but **not
wired into the running application**: `ConsentRegistry` is never instantiated in
`api/deps.py::AppState`, there is no `/consent/*` route, and the main `README.md` doesn't
mention it even though `docs/src/solution-note.html:223-224` already publicly claims "Consent
is enforced at the point of reading, and refusals are logged... follows the DPDP Act 2023 and
ABDM consent artefacts."

This should land **before** any live ABDM data pull is wired up (see
`docs/abdm-ncdir-feasibility.md` §4), so that from the first real (sandbox) record read, access
is consent-gated and logged — not retrofitted after the fact.

## Scope

1. **Add `abha_number: str | None = None`** to `Patient` and `FamilyMember` in
   `backend/saathi/domain/models.py`. This mirrors the key the consent layer and
   `ingest/abdm.py::ABDMClient.care_steps(abha_id, patient_id)` already use as a identifier
   distinct from Saathi's internal `patient_id` — the convention exists, just isn't threaded
   onto `Patient` yet.
2. **Instantiate `ConsentRegistry` inside `AppState`** (`backend/saathi/api/deps.py`), alongside
   the other long-lived, per-process state the app already builds there.
3. **Add `/consent/*` routes** (new `backend/saathi/api/consent.py`, following the existing
   router pattern in `api/family.py`/`api/routes.py`):
   - `POST /consent/request` → `ConsentRegistry.request()`
   - `POST /consent/{id}/grant` → `.grant()`
   - `POST /consent/{id}/revoke` → `.revoke()`
   - `GET /consent/active` → `.active_grants()`
   - `GET /consent/access-log` → `.access_log()`
4. **Gate every ABDM-sourced read through `ConsentRegistry.resolve()`** once `ABDMClient` is
   wired (separate, later ticket) — a call with no active grant should produce a logged refusal
   (`AccessOutcome.NO_CONSENT`/`REVOKED`/`EXPIRED`/`OUT_OF_SCOPE`), not silently return nothing
   or raise.
5. **Add `settings.abdm_enabled`** to `backend/saathi/config.py`, mirroring the existing
   `whatsapp_enabled`/`neo4j_enabled` pattern — today ABDM and the hospital feed are the only
   two integrations without a computed enabled-flag, and `ABDMClient` instantiation (whenever
   that lands) should be gated behind it the same way.

## Explicitly out of scope for this ticket

- The ABDM OAuth client-credentials token exchange and actual `ABDMClient` wiring — separate
  ticket, depends on sandbox credentials existing (see Phase 0 in the feasibility brief).
- Persistence of consent state across restarts — `ConsentRegistry` today is in-memory, same as
  the rest of the app's live state; moving it onto `db/tables.py` is a separate persistence
  effort, not blocking this ticket.
- UI for the consent flow in `console/` — this ticket is API-only.

## Suggested verification

- Extend `tests/test_consent.py` coverage (or add `tests/test_api_consent.py`) to hit the new
  routes directly, not just the `ConsentRegistry` class.
- Manually exercise via the running API (`make api`): request → grant → resolve (should
  succeed) → revoke → resolve again (should produce a logged `AccessAttempt` with
  `AccessOutcome.REVOKED`).
- Confirm the access log entries are visible in the existing evidence-ledger hash chain (same
  integrity check the app already runs — see `GET /api/health`'s `ledger_intact` field).
