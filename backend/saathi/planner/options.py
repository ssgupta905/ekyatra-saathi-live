"""Ranked re-plan options for a disrupted patient.

This module enumerates *candidates*; it does not decide anything. Each
candidate's decision still comes from `tools.decide()`, called exactly as
`planner/graph.py`'s own `_decide` node calls it — this file only builds the
hypothetical step lists `decide()` is asked to judge, and measures the
tradeoff between each candidate and the pre-disruption baseline. Nothing here
is more of a "decision authority" than `graph.py` already is; it is the same
deterministic pipeline, run more than once.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from ..domain.enums import Decision, StepKind
from ..domain.models import CareStep, Disruption, MaintenanceCycle, Patient, PlanOption
from ..graph.dependencies import DependencyGraph
from ..readiness.conformal import ConformalReadinessPredictor
from . import tools
from .care_rules import filter_options


def _build_option(
    patient: Patient,
    steps: Sequence[CareStep],
    target_kind: StepKind,
    graph: DependencyGraph,
    predictor: ConformalReadinessPredictor,
    today: date,
    *,
    nights_added: int = 0,
    extra_trips: int = 0,
    dose_delay_days: int = 0,
    disruptions: Sequence[Disruption] = (),
) -> PlanOption | None:
    target = tools.find_step(steps, target_kind)
    if target is None:
        return None
    unmet = tools.unmet_prerequisites(target, steps, graph)
    missing = tools.missing_prerequisite_kinds(target, steps, graph)
    # The same disruptions the live plan is judged under: a candidate that
    # re-books onto a machine that is still down must not come back GO.
    blockers = tools.describe_blockers(unmet, predictor, disruptions)
    decision = tools.decide(blockers, missing, today)
    is_go = decision is Decision.GO
    travel_on = tools.earliest_safe_travel_date(blockers, today) if is_go else None
    bundled = tools.bundle_steps(target, steps, graph) if is_go else ()
    bundled_kinds = [s.kind for s in steps if s.id in bundled]
    return PlanOption(
        patient_id=patient.id,
        target_step_id=target.id,
        decision=decision,
        travel_on=travel_on,
        bundled_step_ids=bundled,
        blocked_by=blockers,
        what_to_bring=tools.documents_to_bring(target, bundled_kinds) if is_go else (),
        where_to_go_first=tools.where_to_go_first(target, bundled_kinds) if is_go else None,
        rationale=_rationale(decision, blockers),
        nights_added=nights_added,
        extra_trips=extra_trips,
        dose_delay_days=dose_delay_days,
    )


def _rationale(decision: Decision, blockers: Sequence) -> str:
    if decision is Decision.GO:
        return "every prerequisite is satisfied on the shifted date"
    if decision is Decision.WAIT:
        return f"still waiting on {len(blockers)} prerequisite(s) on the shifted date"
    return "insufficient calibrated evidence on the shifted date; no date promised"


def _affected_step_ids(steps: Sequence[CareStep], disruption: Disruption) -> set[str]:
    return {
        s.id
        for s in steps
        if s.resource_id == disruption.resource_id
        and s.scheduled_for is not None
        and s.scheduled_for >= disruption.unavailable_from
        and (disruption.unavailable_to is None or s.scheduled_for <= disruption.unavailable_to)
    }


def _shift(steps: Sequence[CareStep], step_ids: set[str], to: date) -> list[CareStep]:
    return [s.model_copy(update={"scheduled_for": to}) if s.id in step_ids else s for s in steps]


#: A documented, deterministic ranking — fewest extra trips, then fewest
#: nights, then least delay. Never a stored composite score (invariant 7):
#: this is a sort key computed at read time, not a field on `PlanOption`.
def _rank_key(option: PlanOption) -> tuple[int, int, int]:
    return (option.extra_trips, abs(option.nights_added), option.dose_delay_days)


def enumerate_candidates(
    patient: Patient,
    steps: Sequence[CareStep],
    disruption: Disruption,
    target_kind: StepKind,
    graph: DependencyGraph,
    predictor: ConformalReadinessPredictor,
    today: date,
    *,
    cycle: MaintenanceCycle | None = None,
) -> tuple[PlanOption, ...]:
    """Ranked candidates for one patient hit by `disruption`.

    Two shapes, matching the brief's option tables:
    - **Bundled**: the disrupted step(s) move to the first day the resource
      is free again; everything else, including the target visit, stays
      where it was if it still fits — zero or few extra trips.
    - **Split**: the family leaves now and returns later for the delayed
      step — never any nights added to the current stay, but an extra round
      trip. Only offered when the delay would otherwise be long enough that
      waiting in the city is itself costly (more than `_SPLIT_THRESHOLD_DAYS`).
    """
    affected = _affected_step_ids(steps, disruption)
    if not affected:
        return ()

    resume_on = (disruption.unavailable_to or disruption.unavailable_from) + timedelta(days=1)
    original_target = tools.find_step(steps, target_kind)
    baseline_travel = original_target.scheduled_for if original_target else None

    candidates: list[PlanOption] = []

    bundled_steps = _shift(steps, affected, resume_on)
    dose_delay = 0
    if cycle is not None and target_kind is StepKind.MAINTENANCE_DOSE and baseline_travel:
        dose_delay = (resume_on - baseline_travel).days
    bundled_option = _build_option(
        patient, bundled_steps, target_kind, graph, predictor, today,
        nights_added=0, extra_trips=0, dose_delay_days=max(dose_delay, 0),
    )
    if bundled_option is not None:
        candidates.append(bundled_option)

    delay_days = (resume_on - today).days
    if delay_days > _SPLIT_THRESHOLD_DAYS and baseline_travel is not None:
        split_steps = _shift(steps, affected, resume_on)
        split_option = _build_option(
            patient, split_steps, target_kind, graph, predictor, today,
            nights_added=-delay_days, extra_trips=2, dose_delay_days=max(dose_delay, 0),
        )
        if split_option is not None:
            candidates.append(split_option)

    candidates.sort(key=_rank_key)
    return filter_options(tuple(candidates), cycle)


#: Below this many days, waiting in the city is cheaper than two more trips.
_SPLIT_THRESHOLD_DAYS = 3


def opportunistic_bundle_candidates(
    patient: Patient,
    steps: Sequence[CareStep],
    disruption: Disruption,
    target_kind: StepKind,
    graph: DependencyGraph,
    predictor: ConformalReadinessPredictor,
    today: date,
    *,
    cycle: MaintenanceCycle | None = None,
) -> tuple[PlanOption, ...]:
    """When the family is already booked for a *different* nearby visit,
    propose moving the delayed step onto it instead of a fresh trip.

    This is how a stock delay can end up *better* than the original plan:
    one trip instead of two, even though the step itself lands a little
    later. Still routes every candidate through `tools.decide()` like
    `enumerate_candidates` does — it only changes which date is tried.
    """
    affected = _affected_step_ids(steps, disruption)
    if not affected:
        return ()

    target = tools.find_step(steps, target_kind)
    if target is None:
        return ()

    other_visits = sorted(
        {
            s.scheduled_for
            for s in steps
            if s.id not in affected
            and s.scheduled_for is not None
            and s.scheduled_for >= today
            and graph.can_share_trip(s.kind, target_kind)
        }
    )
    earliest_shared = next(
        (d for d in other_visits if d >= disruption.unavailable_from), None
    )
    if earliest_shared is None:
        return ()

    baseline_travel = target.scheduled_for
    shifted = _shift(steps, affected, earliest_shared)
    dose_delay = (earliest_shared - baseline_travel).days if baseline_travel else 0
    option = _build_option(
        patient, shifted, target_kind, graph, predictor, today,
        nights_added=0, extra_trips=-1, dose_delay_days=max(dose_delay, 0),
    )
    if option is None:
        return ()
    return filter_options((option,), cycle)
