"""End-to-end planner behaviour on constructed journeys.

These are the cases the deck promises: never travel for a step that is not
ready, bundle what can be bundled, and promise nothing when uncertain.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import pytest
from saathi.domain.enums import Decision, Language, StepKind, StepStatus
from saathi.domain.models import CareStep, Patient
from saathi.planner.graph import VisitPlanner
from saathi.readiness.conformal import ConformalReadinessPredictor, TurnaroundSample

TODAY = date(2026, 3, 10)
FIRST_VISIT = TODAY - timedelta(days=5)


@pytest.fixture
def patient():
    return Patient(
        id="P0001",
        home_distance_km=1900.0,
        home_district="Murshidabad",
        language=Language.BENGALI,
        caregiver_phone="+919900000000",
        hospital_id="TMH-MUM",
    )


@pytest.fixture
def predictor():
    rng = random.Random(42)
    samples = []
    for queue, median in (("pathology_report", 7.0), ("radiology_report", 3.0)):
        for _ in range(200):
            samples.append(
                TurnaroundSample(queue=queue, days=max(1.0, round(rng.gauss(median, 1.5))))
            )
    return ConformalReadinessPredictor(alpha=0.1).fit(samples)


@pytest.fixture
def planner(predictor):
    # No language layer: the decision path is what these tests exercise.
    return VisitPlanner(predictor=predictor, language_layer=None)


def _steps(path_status, rad_status, include_reports=True):
    steps = [
        CareStep(id="P0001-consult", patient_id="P0001", kind=StepKind.CONSULT,
                 status=StepStatus.COMPLETED, completed_on=FIRST_VISIT, queue="consult"),
        CareStep(id="P0001-biopsy", patient_id="P0001", kind=StepKind.BIOPSY,
                 status=StepStatus.COMPLETED, completed_on=FIRST_VISIT, queue="biopsy"),
        CareStep(id="P0001-bloods", patient_id="P0001", kind=StepKind.BLOODS,
                 status=StepStatus.COMPLETED, completed_on=FIRST_VISIT, queue="bloods"),
        CareStep(id="P0001-scan", patient_id="P0001", kind=StepKind.SCAN,
                 status=StepStatus.COMPLETED, completed_on=FIRST_VISIT, queue="scan"),
        CareStep(id="P0001-review", patient_id="P0001", kind=StepKind.REVIEW_CONSULT,
                 status=StepStatus.SCHEDULED, scheduled_for=TODAY + timedelta(days=2),
                 queue="review_consult"),
    ]
    if include_reports:
        steps.insert(4, CareStep(
            id="P0001-pathology_report", patient_id="P0001", kind=StepKind.PATHOLOGY_REPORT,
            status=path_status, completed_on=FIRST_VISIT, queue="pathology_report",
            result_available_on=TODAY if path_status is StepStatus.RESULT_AVAILABLE else None,
        ))
        steps.insert(5, CareStep(
            id="P0001-radiology_report", patient_id="P0001", kind=StepKind.RADIOLOGY_REPORT,
            status=rad_status, completed_on=FIRST_VISIT, queue="radiology_report",
            result_available_on=TODAY if rad_status is StepStatus.RESULT_AVAILABLE else None,
        ))
    return steps


def test_go_when_every_report_has_landed(planner, patient):
    steps = _steps(StepStatus.RESULT_AVAILABLE, StepStatus.RESULT_AVAILABLE)
    result = planner.plan_visit(patient, steps, StepKind.REVIEW_CONSULT, today=TODAY)

    plan = result["plan"]
    assert plan.decision is Decision.GO
    assert plan.travel_on is not None
    assert plan.where_to_go_first
    assert plan.what_to_bring


def test_wait_when_a_report_is_still_pending(planner, patient):
    """The wasted second trip in the deck. This is the case that must not GO."""
    steps = _steps(StepStatus.PENDING_RESULT, StepStatus.RESULT_AVAILABLE)
    result = planner.plan_visit(patient, steps, StepKind.REVIEW_CONSULT, today=TODAY)

    plan = result["plan"]
    assert plan.decision is Decision.WAIT
    assert plan.travel_on is None, "a WAIT plan must never carry a date"
    assert [b.kind for b in plan.blocked_by] == [StepKind.PATHOLOGY_REPORT]


def test_wait_plan_reports_a_calibrated_window(planner, patient):
    steps = _steps(StepStatus.PENDING_RESULT, StepStatus.RESULT_AVAILABLE)
    result = planner.plan_visit(patient, steps, StepKind.REVIEW_CONSULT, today=TODAY)

    window = result["plan"].blocked_by[0].expected_ready
    assert window is not None and window.calibrated
    assert window.earliest <= window.latest


def test_uncertain_when_the_predictor_is_uncalibrated(patient):
    """Thin turnaround history must produce no date, not a confident guess."""
    thin = ConformalReadinessPredictor(alpha=0.1).fit(
        [TurnaroundSample("pathology_report", 7.0)] * 3
    )
    planner = VisitPlanner(predictor=thin, language_layer=None)
    steps = _steps(StepStatus.PENDING_RESULT, StepStatus.RESULT_AVAILABLE)
    result = planner.plan_visit(patient, steps, StepKind.REVIEW_CONSULT, today=TODAY)

    plan = result["plan"]
    assert plan.decision is Decision.UNCERTAIN
    assert plan.travel_on is None
    assert result["escalation"]


def test_uncertain_when_a_prerequisite_has_no_record(planner, patient):
    steps = _steps(StepStatus.RESULT_AVAILABLE, StepStatus.RESULT_AVAILABLE,
                   include_reports=False)
    result = planner.plan_visit(patient, steps, StepKind.REVIEW_CONSULT, today=TODAY)

    assert result["plan"].decision is Decision.UNCERTAIN
    assert result["plan"].travel_on is None


def test_missing_target_step_escalates(planner, patient):
    steps = _steps(StepStatus.RESULT_AVAILABLE, StepStatus.RESULT_AVAILABLE)
    steps = [s for s in steps if s.kind is not StepKind.TREATMENT]
    result = planner.plan_visit(patient, steps, StepKind.TREATMENT, today=TODAY)

    assert result["plan"].decision is Decision.UNCERTAIN
    assert "treatment" in result["escalation"]


def test_first_visit_bundles_consult_biopsy_and_bloods(planner, patient):
    """Four trips become two because these three collapse into one visit."""
    steps = [
        CareStep(id="P0001-consult", patient_id="P0001", kind=StepKind.CONSULT,
                 status=StepStatus.SCHEDULED, scheduled_for=TODAY, queue="consult"),
        CareStep(id="P0001-biopsy", patient_id="P0001", kind=StepKind.BIOPSY,
                 status=StepStatus.NOT_SCHEDULED, queue="biopsy"),
        CareStep(id="P0001-bloods", patient_id="P0001", kind=StepKind.BLOODS,
                 status=StepStatus.NOT_SCHEDULED, queue="bloods"),
    ]
    result = planner.plan_visit(patient, steps, StepKind.CONSULT, today=TODAY)

    plan = result["plan"]
    assert plan.decision is Decision.GO
    assert set(plan.bundled_step_ids) == {"P0001-biopsy", "P0001-bloods"}


def test_every_plan_is_backed_by_ledger_evidence(planner, patient):
    steps = _steps(StepStatus.RESULT_AVAILABLE, StepStatus.RESULT_AVAILABLE)
    result = planner.plan_visit(patient, steps, StepKind.REVIEW_CONSULT, today=TODAY)

    plan = result["plan"]
    assert plan.evidence
    assert planner.ledger.resolve_all(plan.evidence)
    assert planner.ledger.verify()
