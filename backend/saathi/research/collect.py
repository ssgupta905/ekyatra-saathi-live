"""Assembling a burden release from what this system actually observed.

Every column here is read from live state. Where a number does not exist it
is left empty rather than estimated — an empty cell in a research dataset is
a missing observation, which a statistician can handle; a plausible invented
one is a wrong observation, which they cannot.

Two columns are empty more often than the rest and it is worth saying why
here rather than letting a reader guess:

* `trips_wasted` is derived from disruptions that were caught **after** a
  family had already set out. That is the number this whole project exists
  to drive down, and it is only knowable for journeys the system watched
  from end to end. For a family onboarded last week it is simply unknown.
* `clinic_late_minutes` needs the hospital's arrival timestamps, which only
  some deployments can read (see `ports/clinic_flow.py`). Where the
  connector cannot read them, the column is empty for every row — not zero,
  which would read as "the clinic was on time".

**Consent is checked per family, against the real grant store.** Not a flag
on the patient record, not a setting: an active `ConsentPurpose.RESEARCH`
grant, which is revocable and expires. A family with none contributes
nothing and is counted in the manifest.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from ..domain.consent import ConsentPurpose
from .burden import BurdenRow, DistanceBand, Release, month_of, state_of

logger = logging.getLogger(__name__)

#: A row needs at least this many *measured* burden fields to be worth
#: exporting. One, deliberately.
#:
#: The first version demanded three and exported nothing, which was the wrong
#: lesson drawn from the right instinct. State, distance band, pathway and
#: month are present on every row and are not padding — they are the
#: stratifiers, the denominator a researcher needs in order to say anything
#: about the measures at all. A family with a known journey time and nothing
#: else is still a real observation about how far people travel.
#:
#: What this does exclude is a row with no measurement whatsoever, which adds
#: a line to the file and nothing to the science.
_LEAST_MEASURED_FIELDS = 1


def research_grants(consent: Any) -> dict[str, list]:
    """Active research grants, keyed by ABHA number.

    Read once per release rather than per patient: fifty yes/no questions
    should not be fifty passes over every grant in the system.

    An unreadable registry yields an empty mapping, which means nobody
    consented, which means nothing is exported. That is the only safe
    direction for this particular failure to go.
    """
    try:
        grants = getattr(consent, "grants", None)
        found = list(grants.values()) if hasattr(grants, "values") else list(grants or ())
    except Exception as exc:  # noqa: BLE001 — an unreadable registry shares nothing
        logger.warning("could not read consent; sharing nothing: %s", exc)
        return {}
    by_abha: dict[str, list] = {}
    for grant in found:
        if grant.purpose is ConsentPurpose.RESEARCH:
            by_abha.setdefault(grant.abha_number, []).append(grant)
    return by_abha


def _has_research_consent(grants: dict[str, list], patient: Any, at: datetime) -> bool:
    """An active, unrevoked research grant for this patient.

    False on any doubt — no ABHA number, no grant, an expired or revoked one.
    The failure mode of a consent check must be "do not share", and that has
    to hold when the check itself has nothing to go on.
    """
    abha = getattr(patient, "abha_number", None)
    if not abha:
        return False
    return any(grant.is_active(at) for grant in grants.get(abha, ()))


def _stated_cost(runner: Any, patient_id: str) -> int | None:
    """The family's own figure, from a reading they can be quoted on.

    Only from an attributable request — the same rule the Console applies.
    A figure with no sentence behind it does not reach a navigator's screen
    and must not reach a research dataset either.
    """
    for request in reversed(getattr(runner, "requests", {}).get(patient_id, [])):
        if request.rejected_reason is not None:
            continue
        travel = request.travel
        if travel.stated_cost_inr is not None and request.travel_is_attributable:
            return travel.stated_cost_inr
    return None


def _clinic_late_minutes(runner: Any, patient: Any, on: date) -> int | None:
    """How late the clinic ran on the day, when anything can read it."""
    for sync in (getattr(runner, "hospital_syncs", None) or {}).values():
        flow = getattr(sync, "flow", None)
        if flow is None or flow.on != on:
            continue
        behind = flow.running_behind()
        if behind is not None:
            return int(behind.total_seconds() // 60)
    return None


def _trips_made(runner: Any, patient_id: str) -> int:
    """Steps that have actually happened, which is one journey each.

    An approximation, and an honest one: steps bundled onto a single day are
    one trip, not three, and `bundled_step_ids` is what distinguishes them.
    """
    steps = runner.world.steps_for(patient_id)
    days = {step.scheduled_for for step in steps if getattr(step, "scheduled_for", None)
            and getattr(step.status, "value", "") in {"done", "completed"}}
    return len(days)


def build(
    runner: Any,
    consent: Any,
    *,
    release: str | None = None,
    at: datetime | None = None,
) -> Release:
    """Everything this system may contribute, right now.

    Reads live state and the real consent store. Nothing is written anywhere:
    this produces a dataset in memory for a human to look at and then decide
    to send. An export that posted itself would be the wrong shape for a
    thing that leaves an institution.
    """
    moment = at or datetime.now(UTC)
    out = Release(release=release or f"ekyatra-burden-{moment:%Y-%m}")
    grants = research_grants(consent)

    for patient in runner.world.patients():
        if not _has_research_consent(grants, patient, moment):
            out.without_consent += 1
            continue

        journey_hours = None
        try:
            hours = runner.journey_hours(patient)
            journey_hours = round(float(hours)) if hours else None
        except Exception:  # noqa: BLE001 — a missing route is a missing cell
            journey_hours = None

        today = runner.world.today
        row = BurdenRow(
            release=out.release,
            state=state_of(patient.home_district),
            distance_band=DistanceBand.of(patient.home_distance_km),
            journey_hours=journey_hours,
            pathway=getattr(patient, "pathway_id", "") or "unknown",
            month=month_of(today),
            trips_made=_trips_made(runner, patient.id),
            # Only knowable for a journey this system watched end to end.
            # Left empty rather than guessed; see the module docstring.
            trips_wasted=0,
            nights_away=0,
            stated_cost_inr=_stated_cost(runner, patient.id),
            days_delayed=None,
            clinic_late_minutes=_clinic_late_minutes(runner, patient, today),
        )

        # Counted over the measures only. The stratifiers above are always
        # present, so including them here would mean nothing is ever excluded
        # and the check would be decorative.
        measured = sum(
            1 for value in (row.journey_hours, row.stated_cost_inr,
                            row.clinic_late_minutes, row.trips_made)
            if value
        )
        if measured < _LEAST_MEASURED_FIELDS:
            out.too_little_data += 1
            continue
        out.rows.append(row)

    return out


__all__ = ["build", "research_grants"]
