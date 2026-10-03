"""A journey has to be bookable, not merely affordable.

Counting trips treats "go home and come back on Monday" as costing two train
journeys. For a family 1,771 km from the hospital it may cost something else
entirely: a reserved berth from Gaya to Mumbai cannot be had the day after
tomorrow, so that option may be describing a journey that does not exist.

A family told to travel on a train they cannot board has been failed worse than
one told to wait, so an option needing short-notice travel ranks below one that
merely costs a trip — and for a family 90 km away, where travel is a bus taken
on the day, it costs nothing and must not be penalised at all.
"""

from __future__ import annotations

from datetime import date, timedelta

from saathi.domain.enums import StepKind, StepStatus
from saathi.domain.models import CareStep
from saathi.domain.policy import HospitalPolicy
from saathi.planner.itinerary import short_notice_journeys

TODAY = date(2026, 11, 12)


def _step(kind: StepKind, on: date, suffix: str = "") -> CareStep:
    return CareStep(
        id=f"P1-{kind.value}{suffix}",
        patient_id="P1",
        kind=kind,
        status=StepStatus.SCHEDULED,
        scheduled_for=on,
    )


def test_a_journey_sooner_than_a_reservation_is_counted():
    # The family goes home and must come back in two days; reservations here
    # need three.
    steps = [
        _step(StepKind.SCAN, TODAY + timedelta(days=2)),
        _step(StepKind.REVIEW_CONSULT, TODAY + timedelta(days=12)),
    ]

    assert short_notice_journeys(steps, not_before=TODAY, lead_days=3) == 1


def test_a_journey_with_enough_notice_is_not_counted():
    steps = [
        _step(StepKind.SCAN, TODAY + timedelta(days=6)),
        _step(StepKind.REVIEW_CONSULT, TODAY + timedelta(days=16)),
    ]

    assert short_notice_journeys(steps, not_before=TODAY, lead_days=3) == 0


def test_only_arrivals_count_not_the_journey_home():
    """The trip home is taken from the hospital and can be booked days ahead.

    It is the journey *to* a date that was just moved which may have no berth
    left on it, so a plan with one short-notice arrival counts one, not two.
    """
    steps = [_step(StepKind.SCAN, TODAY + timedelta(days=1))]

    assert short_notice_journeys(steps, not_before=TODAY, lead_days=3) == 1


def test_a_long_journey_needs_a_reservation():
    policy = HospitalPolicy(hospital_id="TMH-MUM")

    # Gaya to Mumbai and back: about 40 hours each way.
    assert policy.needs_reservation(80.0) is True
    # Samastipur to Muzaffarpur: a bus taken on the day.
    assert policy.needs_reservation(3.0) is False


def test_an_unknown_journey_is_assumed_to_need_one():
    """Warning a family to book early when they did not have to costs nothing;
    staying quiet when they did costs them the trip."""
    assert HospitalPolicy(hospital_id="TMH-MUM").needs_reservation(None) is True


def test_a_hospital_can_set_its_own_notice():
    """Corridors and seasons differ, so this is configuration rather than a
    number the planner asserts on a hospital's behalf."""
    policy = HospitalPolicy(hospital_id="TMH-MUM", reservation_lead_days=10)
    steps = [_step(StepKind.SCAN, TODAY + timedelta(days=6))]

    assert short_notice_journeys(steps, not_before=TODAY, lead_days=3) == 0
    assert short_notice_journeys(
        steps, not_before=TODAY, lead_days=policy.reservation_lead_days
    ) == 1


def test_unbookable_ranks_below_merely_expensive():
    from saathi.domain.enums import Decision
    from saathi.domain.models import PlanOption
    from saathi.planner.options import _rank_key

    def option(**kw) -> PlanOption:
        return PlanOption(
            patient_id="P1", target_step_id="P1-scan", decision=Decision.GO, **kw
        )

    costs_a_trip = option(extra_trips=2, nights_added=-3)
    cannot_be_booked = option(extra_trips=0, nights_added=0, short_notice_journeys=1)

    assert _rank_key(costs_a_trip) < _rank_key(cannot_be_booked)
