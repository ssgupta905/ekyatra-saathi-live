"""Placing steps on dates a resource can actually honour.

The brief describes the Planner as a solver that "places each step in the right
order with the fewest trips and nights away". This is that placer, and it is
deliberately small and deterministic: a topological walk of the dependency DAG
that puts each displaced step on the earliest day its resource is free and its
prerequisites are behind it.

It decides nothing. It produces *candidate step lists*; `tools.decide()` judges
each one exactly as it judges the live plan, which is why adding a scheduler
does not move the go/wait authority anywhere. The same rule as `options.py`: a
module may propose, only `decide()` disposes.

Two behaviours carry the stories:

* **Resume** — a step on a broken machine moves to the first day the machine is
  back, and anything downstream that would now run too early moves with it.
* **Co-locate** — steps the dependency graph marks shareable are pulled onto the
  same day when they can be. This is the difference between the brief's option A
  (PET-CT two days after the MRI, pushing the joint clinic out four days) and
  option B (PET-CT the same afternoon, joint clinic untouched). The whole value
  of the option table is in that one distinction, and it is structural, not a
  label.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from ..domain.enums import TRAVEL_STEPS, StepStatus
from ..domain.models import CareStep, Disruption
from ..domain.policy import HospitalPolicy
from ..graph.dependencies import DependencyGraph
from ..readiness.bookings import NoFreeDate, first_free_date, is_cancelled_by

#: Statuses that can still be moved. A completed step is history.
MOVABLE = frozenset({StepStatus.SCHEDULED, StepStatus.NOT_SCHEDULED})


@dataclass(frozen=True)
class ResourceCalendar:
    """When each named resource is available, derived from open disruptions."""

    disruptions: tuple[Disruption, ...] = ()

    @classmethod
    def from_disruptions(cls, disruptions: Iterable[Disruption]) -> ResourceCalendar:
        return cls(tuple(disruptions))

    def first_free(self, resource_id: str | None, not_before: date) -> date | None:
        """Earliest date on or after `not_before` the resource can be booked.

        None when the resource is out with no known return date — there is no
        honest date to offer, and the caller must not invent one.
        """
        try:
            return first_free_date(resource_id, self.disruptions, not_before)
        except NoFreeDate:
            return None

    def is_cancelled(self, step: CareStep) -> bool:
        return is_cancelled_by(step, self.disruptions)


def cancelled_steps(
    steps: Iterable[CareStep], calendar: ResourceCalendar
) -> tuple[str, ...]:
    """Ids of booked steps whose date the hospital can no longer honour."""
    return tuple(step.id for step in steps if calendar.is_cancelled(step))


def displaced_steps(
    steps: Sequence[CareStep],
    calendar: ResourceCalendar,
    graph: DependencyGraph,
) -> tuple[str, ...]:
    """Cancelled steps, plus everything downstream that has to move with them.

    A broken MRI does not only move the MRI. The PET-CT that follows it and the
    clinic that discusses the PET-CT are both displaced, and a candidate that
    re-places only the cancelled step is not a plan — it is a plan with a hole.
    Returning the full set is also what lets `colocate` pull the PET-CT onto the
    MRI's new day, which is the whole of the brief's option B.
    """
    cancelled = set(cancelled_steps(steps, calendar))
    if not cancelled:
        return ()
    hit_kinds = {s.kind for s in steps if s.id in cancelled}
    displaced = set(cancelled)
    for step in steps:
        if step.status not in MOVABLE or step.id in displaced:
            continue
        if graph.transitive_prerequisites(step.kind) & hit_kinds:
            displaced.add(step.id)
    return tuple(s.id for s in steps if s.id in displaced)


def _prerequisite_floor(
    step: CareStep,
    placed: dict[str, CareStep],
    graph: DependencyGraph,
    not_before: date,
    policy: HospitalPolicy,
    *,
    colocate: bool = False,
) -> date:
    """The earliest this step may sit, given what must happen before it.

    Lead times and standing-meeting days come from the hospital's own policy,
    not from a constant in this module. Change the joint clinic from Tuesday
    and Friday to Monday and Thursday in the admin console and this function
    returns different dates — which is the test of whether anything here was
    ever computed.
    """
    floor = not_before
    for kind in graph.transitive_prerequisites(step.kind):
        for other in placed.values():
            if other.kind is not kind or other.scheduled_for is None:
                continue
            # Same-day only when the graph says the two can share a trip *and*
            # this candidate is trying to bundle them. Otherwise the hospital's
            # lead time applies.
            if colocate and graph.can_share_trip(other.kind, step.kind):
                offset = 0
            else:
                offset = policy.lead_days(other.kind, step.kind)
            floor = max(floor, other.scheduled_for + timedelta(days=offset))
    return policy.next_slot(step.kind, floor)


def place(
    steps: Sequence[CareStep],
    calendar: ResourceCalendar,
    graph: DependencyGraph,
    not_before: date,
    policy: HospitalPolicy,
    *,
    move: Iterable[str] | None = None,
    colocate: bool = False,
) -> tuple[CareStep, ...]:
    """Re-place `move` (default: everything the calendar has cancelled).

    Returns a new tuple; `CareStep` is frozen and nothing is mutated. Steps not
    being moved keep their dates, so a candidate differs from the baseline only
    where it had to.

    With `colocate`, a moved step is pulled onto the day of an already-placed
    step it can share a trip with, when its resource is free that day. That is
    what turns two visits into one.
    """
    movable = set(move) if move is not None else set(cancelled_steps(steps, calendar))
    if not movable:
        return tuple(steps)

    # Fixed points first, so prerequisite floors are known before anything moves.
    placed: dict[str, CareStep] = {
        s.id: s for s in steps if s.id not in movable or s.status not in MOVABLE
    }
    pending = [s for s in steps if s.id in movable and s.status in MOVABLE]

    # Topological-ish: a step whose prerequisites are already placed goes next.
    # Falls back to date order so the loop always terminates on a cyclic or
    # under-specified graph rather than spinning.
    pending.sort(key=lambda s: (s.scheduled_for or not_before, s.id))

    for step in pending:
        floor = _prerequisite_floor(step, placed, graph, not_before, policy, colocate=colocate)
        target: date | None = None

        if colocate:
            shared = sorted(
                other.scheduled_for
                for other in placed.values()
                if other.scheduled_for is not None
                and other.scheduled_for >= floor
                and other.kind in TRAVEL_STEPS
                and graph.can_share_trip(other.kind, step.kind)
            )
            for day in shared:
                if calendar.first_free(step.resource_id, day) == day:
                    target = day
                    break

        if target is None:
            target = calendar.first_free(step.resource_id, floor)

        if target is None:
            # No honest date for this resource. Leave the step unscheduled so
            # `decide()` sees an unbounded blocker and returns UNCERTAIN.
            placed[step.id] = step.model_copy(
                update={"status": StepStatus.NOT_SCHEDULED, "scheduled_for": None}
            )
            continue

        placed[step.id] = step.model_copy(
            update={"status": StepStatus.SCHEDULED, "scheduled_for": target}
        )

    return tuple(placed[s.id] for s in steps)


def shift_dependents(
    steps: Sequence[CareStep],
    graph: DependencyGraph,
    not_before: date,
    policy: HospitalPolicy,
) -> tuple[CareStep, ...]:
    """Push any step that now sits before a prerequisite back behind it.

    Called after `place` when a moved step overtook something downstream of it.
    Only ever moves dates later, never earlier — a plan must not quietly bring a
    visit forward under a family that has already booked travel for it.
    """
    placed = {s.id: s for s in steps}
    for step in sorted(steps, key=lambda s: (s.scheduled_for or not_before, s.id)):
        if step.scheduled_for is None or step.status not in MOVABLE:
            continue
        floor = _prerequisite_floor(step, placed, graph, not_before, policy)
        if step.scheduled_for < floor:
            placed[step.id] = step.model_copy(update={"scheduled_for": floor})
    return tuple(placed[s.id] for s in steps)
