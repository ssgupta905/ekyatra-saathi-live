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
from . import care_rules, itinerary, schedule, tools
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
    short_notice_journeys: int = 0,
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
        target_on=target.scheduled_for,
        decision=decision,
        travel_on=travel_on,
        bundled_step_ids=bundled,
        blocked_by=blockers,
        what_to_bring=tools.documents_to_bring(target, bundled_kinds) if is_go else (),
        where_to_go_first=tools.where_to_go_first(target, bundled_kinds) if is_go else None,
        rationale=_rationale(decision, blockers),
        nights_added=nights_added,
        extra_trips=extra_trips,
        short_notice_journeys=short_notice_journeys,
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
def _rank_key(option: PlanOption) -> tuple[int, int, int, int]:
    """Order the options. Deterministic, documented, and not a score.

    Unbookable before expensive: an option that needs a reserved berth sooner
    than one can be obtained may not be a plan at all, so it ranks below one
    that merely costs a trip. Below that the trade is the old one — trips,
    then nights, then a delayed dose — and a person still chooses.
    """
    return (
        option.short_notice_journeys,
        option.extra_trips,
        abs(option.nights_added),
        option.dose_delay_days,
    )


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


def candidates_for_request(
    patient: Patient,
    steps: Sequence[CareStep],
    request,
    target_kind: StepKind,
    graph: DependencyGraph,
    predictor: ConformalReadinessPredictor,
    today: date,
    policy,
    *,
    disruptions: Sequence[Disruption] = (),
    cycle: MaintenanceCycle | None = None,
    round_trip_hours: float | None = None,
) -> tuple[PlanOption, ...]:
    """Re-plan around what a family said they cannot do.

    Three shapes get tried, and the third is the one that matters:

    * **What they asked for** — the first slot on or after the date they
      proposed.
    * **The edge of what is allowed** — the latest date still inside the
      hospital's stated tolerance, when their proposal falls outside it.
    * **Earlier** — the last slot before the date they cannot make.

    Offering "earlier" is the whole point. A family asking to delay ten days is
    often asking for the only thing they could think of, and moving the visit
    three days forward can clear the wedding *and* keep the schedule. Doing what
    was asked is not the same as helping. What is never offered is a date they
    explicitly ruled out, or one outside the tolerance a clinician set — the
    first would waste their journey and the second would waste the doctor's
    attention on a choice that was never available.
    """
    target = tools.find_step(steps, target_kind)
    if target is None or target.scheduled_for is None:
        return ()

    booked_on = target.scheduled_for
    calendar = schedule.ResourceCalendar.from_disruptions(tuple(disruptions))
    tolerance = policy.shift_tolerance(target_kind)
    excluded = set(request.constraint.excluded_dates)
    gap = policy.gap_days(round_trip_hours)

    wanted: list[date] = []
    if request.constraint.not_before:
        wanted.append(policy.next_slot(target_kind, request.constraint.not_before))
    if tolerance is not None:
        wanted.append(policy.next_slot(target_kind, booked_on + timedelta(days=tolerance)))
        earlier = booked_on - timedelta(days=tolerance)
        # Never propose a date in the past, and never today — a family cannot
        # travel overnight on a message sent this afternoon.
        if earlier > today:
            wanted.append(policy.next_slot(target_kind, earlier))

    seen: set[date] = set()
    candidates: list[PlanOption] = []
    for proposed in wanted:
        if proposed in seen or proposed in excluded or proposed <= today:
            continue
        seen.add(proposed)

        moved = schedule.place(
            steps, calendar, graph, today, policy,
            move=(target.id,), colocate=False,
        )
        moved = tuple(
            s.model_copy(update={"scheduled_for": proposed}) if s.id == target.id else s
            for s in moved
        )
        moved = schedule.shift_dependents(moved, graph, today, policy)

        nights, journeys = itinerary.compare(
            moved, steps, not_before=today, gap_days=gap
        )
        short_notice = (
            itinerary.short_notice_journeys(
                moved, not_before=today, lead_days=policy.reservation_lead_days, gap_days=gap
            )
            if policy.needs_reservation(round_trip_hours)
            else 0
        )
        option = _build_option(
            patient, moved, target_kind, graph, predictor, today,
            nights_added=nights, extra_trips=journeys,
            short_notice_journeys=short_notice,
            dose_delay_days=max((proposed - booked_on).days, 0),
            disruptions=disruptions,
        )
        if option is None:
            continue
        if not care_rules.within_shift_tolerance(option, booked_on, tolerance):
            continue
        candidates.append(option)

    candidates.sort(key=_rank_key)
    return filter_options(tuple(candidates), cycle)
