"""Ranked re-plan options: candidates come from `tools.decide`, never a score.

Constructed journeys, same style as `test_planner.py` — these isolate the
options solver from the live world so the tradeoff arithmetic and the
auto-resolve/human-choice split are each independently checkable.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from saathi.domain.enums import (
    Decision,
    DisruptionKind,
    Language,
    SourceSystem,
    StepKind,
    StepStatus,
)
from saathi.domain.models import CareStep, Disruption, MaintenanceCycle, Patient, PlanOption
from saathi.graph.dependencies import InMemoryDependencyGraph
from saathi.planner import options as options_module
from saathi.planner.care_rules import echo_before_every_fourth_dose, filter_options
from saathi.readiness.conformal import ConformalReadinessPredictor

TODAY = date(2026, 11, 17)


@pytest.fixture
def patient():
    return Patient(
        id="P0099", home_distance_km=120.0, home_district="Samastipur",
        language=Language.HINDI, caregiver_phone="+91X", hospital_id="HBCH-MZP",
    )


@pytest.fixture
def graph():
    return InMemoryDependencyGraph()


@pytest.fixture
def predictor():
    return ConformalReadinessPredictor(alpha=0.1)


#: Every step the pathway requires before `MAINTENANCE_DOSE`, already done —
#: a maintenance patient has long since finished the run-up Story 1 covers.
_COMPLETED_HISTORY: tuple[StepKind, ...] = (
    StepKind.CONSULT,
    StepKind.BIOPSY,
    StepKind.BLOODS,
    StepKind.SCAN,
    StepKind.PATHOLOGY_REPORT,
    StepKind.RADIOLOGY_REPORT,
    StepKind.REVIEW_CONSULT,
    StepKind.TREATMENT,
)


def _dose_steps(
    patient_id: str,
    dose_scheduled: date,
    echo_resource: str,
    echo_scheduled: date,
    dose_resource: str | None = None,
):
    history = [
        CareStep(
            id=f"{patient_id}-{kind.value}", patient_id=patient_id, kind=kind,
            status=StepStatus.COMPLETED, completed_on=TODAY - timedelta(days=200),
            queue=kind.value,
        )
        for kind in _COMPLETED_HISTORY
    ]
    return history + [
        CareStep(id=f"{patient_id}-{StepKind.MAINTENANCE_DOSE.value}", patient_id=patient_id,
                 kind=StepKind.MAINTENANCE_DOSE, status=StepStatus.SCHEDULED,
                 scheduled_for=dose_scheduled, queue="day_care", resource_id=dose_resource),
        CareStep(id=f"{patient_id}-{StepKind.ECHO_REVIEW.value}", patient_id=patient_id,
                 kind=StepKind.ECHO_REVIEW, status=StepStatus.SCHEDULED,
                 scheduled_for=echo_scheduled, queue="cardiology", resource_id=echo_resource),
    ]


def _disruption(resource_id: str, kind: DisruptionKind, start: date, end: date) -> Disruption:
    from datetime import UTC, datetime

    return Disruption(
        id="D1", resource_id=resource_id, kind=kind, raised_by=SourceSystem.HOSPITAL_FEED,
        raised_at=datetime.now(UTC), unavailable_from=start, unavailable_to=end, note="test",
    )


def test_a_short_delay_yields_only_one_candidate(patient, graph, predictor):
    """A delay the family can absorb in the same stay needs no human choice."""
    dose_on = TODAY + timedelta(days=5)
    echo_on = TODAY + timedelta(days=1)
    steps = _dose_steps(patient.id, dose_on, "cardio-1", echo_on)
    disruption = _disruption("cardio-1", DisruptionKind.STAFF_UNAVAILABLE, echo_on, echo_on)

    candidates = options_module.enumerate_candidates(
        patient, steps, disruption, StepKind.MAINTENANCE_DOSE, graph, predictor, TODAY,
    )
    assert len(candidates) == 1
    assert candidates[0].decision is Decision.GO


def test_a_long_delay_offers_a_split_trip_alternative(patient, graph, predictor):
    """Past the threshold, going home and returning becomes a real option too."""
    dose_on = TODAY + timedelta(days=10)
    echo_on = TODAY + timedelta(days=3)
    steps = _dose_steps(patient.id, dose_on, "cardio-1", echo_on)
    disruption = _disruption(
        "cardio-1", DisruptionKind.STAFF_UNAVAILABLE, echo_on, echo_on + timedelta(days=7)
    )

    candidates = options_module.enumerate_candidates(
        patient, steps, disruption, StepKind.MAINTENANCE_DOSE, graph, predictor, TODAY,
    )
    assert len(candidates) == 2
    # Ranked: fewest extra trips first (invariant 7 — order is the only rank).
    assert candidates[0].extra_trips <= candidates[1].extra_trips
    assert any(c.extra_trips > 0 for c in candidates), "no split-trip option offered"


def test_every_candidate_decision_comes_from_tools_decide(patient, graph, predictor):
    dose_on = TODAY + timedelta(days=10)
    echo_on = TODAY + timedelta(days=3)
    steps = _dose_steps(patient.id, dose_on, "cardio-1", echo_on)
    disruption = _disruption(
        "cardio-1", DisruptionKind.STAFF_UNAVAILABLE, echo_on, echo_on + timedelta(days=7)
    )

    with patch("saathi.planner.options.tools.decide", wraps=options_module.tools.decide) as spy:
        candidates = options_module.enumerate_candidates(
            patient, steps, disruption, StepKind.MAINTENANCE_DOSE, graph, predictor, TODAY,
        )
    assert spy.call_count == len(candidates)


def test_no_disruption_affected_steps_yields_no_candidates(patient, graph, predictor):
    steps = _dose_steps(
        patient.id, TODAY + timedelta(days=5), "cardio-1", TODAY + timedelta(days=3)
    )
    disruption = _disruption(
        "some-other-resource", DisruptionKind.STAFF_UNAVAILABLE, TODAY, TODAY + timedelta(days=2)
    )
    assert options_module.enumerate_candidates(
        patient, steps, disruption, StepKind.MAINTENANCE_DOSE, graph, predictor, TODAY,
    ) == ()


def test_opportunistic_bundling_turns_a_delay_into_a_saved_trip(patient, graph, predictor):
    """The stock-late story: moving the dose onto an already-booked visit."""
    dose_on = TODAY + timedelta(days=1)
    steps = _dose_steps(
        patient.id, dose_on, "cardio-1", TODAY + timedelta(days=1), dose_resource="pharmacy-1"
    )
    # Dose depends on a supply that won't arrive until later...
    disruption = _disruption(
        "pharmacy-1", DisruptionKind.STOCK_DELAY, dose_on, dose_on + timedelta(days=5)
    )
    # ...but an echo+review visit is already booked a bit later, co-locatable
    # with the dose per `CO_LOCATABLE`.
    steps = [s.model_copy(update={"scheduled_for": dose_on + timedelta(days=3)})
             if s.kind is StepKind.ECHO_REVIEW else s for s in steps]

    options = options_module.opportunistic_bundle_candidates(
        patient, steps, disruption, StepKind.MAINTENANCE_DOSE, graph, predictor, TODAY,
    )
    assert options
    assert options[0].extra_trips < 0, "the opportunistic option should save a trip"


# ---------------------------------------------------------------- care rules


def test_an_option_without_its_echo_bundle_fails_the_fourth_dose_rule():
    cycle = MaintenanceCycle(patient_id="P0099", dose_index=13, anchor_date=TODAY)
    naked = PlanOption(
        patient_id="P0099", target_step_id="P0099-maintenance_dose", decision=Decision.GO,
    )
    assert not echo_before_every_fourth_dose(naked, cycle)


def test_an_option_with_its_echo_bundle_passes_the_fourth_dose_rule():
    cycle = MaintenanceCycle(patient_id="P0099", dose_index=13, anchor_date=TODAY)
    bundled = PlanOption(
        patient_id="P0099", target_step_id="P0099-maintenance_dose", decision=Decision.GO,
        bundled_step_ids=("P0099-echo_review",),
    )
    assert echo_before_every_fourth_dose(bundled, cycle)


def test_filter_options_drops_the_violating_option_silently():
    cycle = MaintenanceCycle(patient_id="P0099", dose_index=13, anchor_date=TODAY)
    naked = PlanOption(patient_id="P0099", target_step_id="x", decision=Decision.GO)
    bundled = PlanOption(
        patient_id="P0099", target_step_id="x", decision=Decision.GO,
        bundled_step_ids=("x-echo_review",),
    )
    kept = filter_options((naked, bundled), cycle)
    assert bundled in kept
    assert naked not in kept


def test_a_dose_that_does_not_require_an_echo_is_never_filtered():
    cycle = MaintenanceCycle(patient_id="P0099", dose_index=6, anchor_date=TODAY)
    naked = PlanOption(patient_id="P0099", target_step_id="x", decision=Decision.GO)
    assert filter_options((naked,), cycle) == (naked,)
