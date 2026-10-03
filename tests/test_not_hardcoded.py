"""The plan must be computed, not configured into existence.

The failure these guard against is subtle and was briefly real in this
codebase: a constant chosen until the demo printed a nice number. Such a
constant looks like a rule and reads like a computation, but the output was the
input, and nothing can be learned by changing anything.

The test for it is simple and it is the one below — **change an input, and the
answer must move**. If a hospital changes which days its consultants meet and
the option table is unaffected, the option table was never derived from it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from saathi.domain.enums import DisruptionKind, SourceSystem, StepKind
from saathi.domain.models import Disruption
from saathi.domain.policy import HospitalPolicy, StepPolicy, default_policy
from saathi.graph.dependencies import InMemoryDependencyGraph
from saathi.planner.itinerary import compare
from saathi.planner.schedule import (
    ResourceCalendar,
    displaced_steps,
    place,
    shift_dependents,
)
from saathi.synthetic.scripted import seed_shambhu_prasad

TODAY = date(2026, 11, 12)


@pytest.fixture
def world():
    patient, steps, _truth = seed_shambhu_prasad(TODAY)
    disruption = Disruption(
        id="D1",
        resource_id="MRI-2",
        kind=DisruptionKind.MACHINE_DOWN,
        raised_by=SourceSystem.HOSPITAL_FEED,
        raised_at=datetime.now(UTC),
        unavailable_from=TODAY,
        unavailable_to=TODAY + timedelta(days=3),
        note="out of service",
    )
    return patient, steps, ResourceCalendar.from_disruptions((disruption,))


def _replan(steps, calendar, policy, *, colocate=False):
    graph = InMemoryDependencyGraph()
    move = displaced_steps(steps, calendar, graph)
    placed = place(steps, calendar, graph, TODAY, policy, move=move, colocate=colocate)
    return shift_dependents(placed, graph, TODAY, policy)


def _clinic_day(steps) -> date:
    return next(s.scheduled_for for s in steps if s.kind is StepKind.JOINT_CLINIC)


def _with_clinic_weekdays(policy: HospitalPolicy, weekdays: tuple[int, ...]) -> HospitalPolicy:
    clinic = policy.steps[StepKind.JOINT_CLINIC.value]
    return policy.model_copy(
        update={
            "steps": {
                **policy.steps,
                StepKind.JOINT_CLINIC.value: clinic.model_copy(update={"weekdays": weekdays}),
            }
        }
    )


# ---------------------------------------------------------------- policy


def test_changing_the_clinic_days_changes_the_plan(world):
    """The headline check. A standing meeting on different days lands differently."""
    _patient, steps, calendar = world
    tue_fri = _replan(steps, calendar, _with_clinic_weekdays(default_policy("H"), (1, 4)))
    mon_thu = _replan(steps, calendar, _with_clinic_weekdays(default_policy("H"), (0, 3)))

    assert _clinic_day(tue_fri).weekday() in (1, 4)
    assert _clinic_day(mon_thu).weekday() in (0, 3)
    assert _clinic_day(tue_fri) != _clinic_day(mon_thu), (
        "the clinic date ignored the hospital's own meeting days"
    )


def test_changing_the_reporting_lead_changes_the_plan(world):
    """Consultants wanting scans reported sooner should pull the meeting in."""
    _patient, steps, calendar = world
    base = default_policy("H")

    def with_lead(days: int) -> HospitalPolicy:
        clinic = base.steps[StepKind.JOINT_CLINIC.value]
        return base.model_copy(
            update={
                "steps": {
                    **base.steps,
                    StepKind.JOINT_CLINIC.value: clinic.model_copy(
                        update={"lead_days": {StepKind.PET_CT.value: days}}
                    ),
                }
            }
        )

    patient_clinic = _clinic_day(_replan(steps, calendar, with_lead(3)))
    hurried_clinic = _clinic_day(_replan(steps, calendar, with_lead(0)))
    assert hurried_clinic < patient_clinic


def test_an_unstated_rule_assumes_only_ordering(world):
    """With no policy at all, the planner claims nothing but 'after'."""
    _patient, steps, calendar = world
    empty = HospitalPolicy(hospital_id="H")
    replanned = _replan(steps, calendar, empty)

    pet_ct = next(s.scheduled_for for s in replanned if s.kind is StepKind.PET_CT)
    scan = next(s.scheduled_for for s in replanned if s.kind is StepKind.SCAN)
    # One day, because a step cannot precede what it depends on — and nothing
    # further is asserted, because nobody has told us anything further.
    assert pet_ct == scan + timedelta(days=1)


def test_defaults_are_marked_unconfirmed():
    """Nothing ships claiming a clinician agreed to it."""
    policy = default_policy("TMH-MUM")
    assert policy.unconfirmed, "defaults must not present themselves as settled"
    assert all(not p.confirmed for p in policy.steps.values())


# ---------------------------------------------------------------- journeys


def test_the_stay_gap_follows_the_journey_not_the_distance():
    """A family 20 hours away and one 1 hour away behave differently."""
    policy = default_policy("H")
    far = policy.gap_days(round_trip_hours=40.4)   # Gaya to Mumbai, both ways
    near = policy.gap_days(round_trip_hours=2.4)   # Samastipur to Muzaffarpur

    assert far > near, "a 40-hour round trip was treated like a 2-hour one"


def test_an_unknown_journey_is_cautious_not_optimistic():
    """No fetched journey must not become 'they will happily wait a week'."""
    policy = default_policy("H")
    assert policy.gap_days(None) == policy.unknown_journey_gap_days
    assert policy.gap_days(None) < policy.gap_days(40.0)


def test_option_deltas_move_with_policy(world):
    """The numbers a navigator chooses between are derived, not declared."""
    _patient, steps, calendar = world
    tue_fri = _replan(steps, calendar, _with_clinic_weekdays(default_policy("H"), (1, 4)))
    mon_thu = _replan(steps, calendar, _with_clinic_weekdays(default_policy("H"), (0, 3)))

    nights_a, _ = compare(tue_fri, steps, not_before=TODAY, gap_days=10)
    nights_b, _ = compare(mon_thu, steps, not_before=TODAY, gap_days=10)
    assert nights_a != nights_b, "nights added ignored the hospital's meeting days"


def test_a_step_policy_round_trips_through_json():
    """Policy is edited in a console and stored; it has to survive the journey."""
    policy = default_policy("TMH-MUM")
    restored = HospitalPolicy.model_validate_json(policy.model_dump_json())
    assert restored == policy
    assert restored.step(StepKind.JOINT_CLINIC).weekdays == (1, 4)
    assert isinstance(
        restored.steps[StepKind.JOINT_CLINIC.value], StepPolicy
    )
