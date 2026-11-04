"""The journey guide: one ordered chain, one 'now', and a date only when the plan is a GO."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from saathi.domain.enums import (
    Language,
    ReadinessKind,
    ReadinessStatus,
    SourceSystem,
    StepKind,
    StepStatus,
)
from saathi.domain.guide import FamilyAction, StageKind, StageState
from saathi.domain.models import CareStep, Patient, ReadinessItem
from saathi.domain.pathway import DIALYSIS, ONCOLOGY
from saathi.guide import build_guide
from saathi.planner.graph import VisitPlanner

TODAY = date(2026, 3, 10)
EARLIER = TODAY - timedelta(days=5)
NEEDS = (ReadinessKind.INSURANCE, ReadinessKind.TRANSPORT, ReadinessKind.STAY)


@pytest.fixture
def patient():
    return Patient(
        id="P1", home_distance_km=900.0, home_district="Gaya", language=Language.HINDI,
        caregiver_phone="+919900000002", hospital_id="TMH-MUM",
    )


def _item(kind, status, party="Uber", *, alternative=False, detail=""):
    return ReadinessItem(
        id=f"P1-{kind.value}", patient_id="P1", kind=kind, party=party, status=status,
        alternative_available=alternative, detail=detail, source=SourceSystem.PARTNER,
    )


def _steps(*, reports_ready=True):
    def done(kind, status=StepStatus.COMPLETED):
        return CareStep(
            id=f"P1-{kind.value}", patient_id="P1", kind=kind, status=status,
            completed_on=EARLIER, result_available_on=EARLIER, queue=kind.value,
        )

    report_status = StepStatus.RESULT_AVAILABLE if reports_ready else StepStatus.PENDING_RESULT
    rows = [done(k) for k in (StepKind.CONSULT, StepKind.BIOPSY, StepKind.BLOODS, StepKind.SCAN)]
    rows += [done(k, report_status) for k in (StepKind.PATHOLOGY_REPORT, StepKind.RADIOLOGY_REPORT)]
    rows.append(
        CareStep(
            id="P1-review", patient_id="P1", kind=StepKind.REVIEW_CONSULT,
            status=StepStatus.SCHEDULED, scheduled_for=TODAY + timedelta(days=2),
            queue="review_consult",
        )
    )
    return rows


def _guide(patient, *, items=(), reports_ready=True, needs=NEEDS):
    steps = _steps(reports_ready=reports_ready)
    plan = VisitPlanner(language_layer=None).plan_visit(
        patient, steps, StepKind.REVIEW_CONSULT, today=TODAY, compose=False,
        readiness_items=items,
    )["plan"]
    return build_guide(
        patient_id="P1", pathway=ONCOLOGY, steps=steps, plan=plan, items=items, needs=needs
    )


def _stage(guide, kind):
    return next(s for s in guide.stages if s.kind is kind)


def test_a_family_waiting_on_a_report_is_told_nothing_yet_and_given_no_date(patient):
    guide = _guide(patient, reports_ready=False)

    assert guide.now_stage_id == "reports"
    reports = _stage(guide, StageKind.REPORTS)
    assert reports.state is StageState.WAITING and reports.party == "the lab"
    assert reports.action is FamilyAction.NOTHING_YET
    assert reports.window is not None, "a forecast window, never a promise"
    assert _stage(guide, StageKind.VISIT).on is None


def test_exactly_one_stage_is_now_and_it_is_the_first_not_done(patient):
    guide = _guide(patient, reports_ready=False)

    assert [s.id for s in guide.stages if s.is_now] == [guide.now_stage_id]
    first_open = next(s for s in guide.stages if s.state is not StageState.DONE)
    assert first_open.id == guide.now_stage_id


def test_parties_not_yet_asked_show_as_coming_not_missing(patient):
    guide = _guide(patient)

    for kind in (StageKind.INSURANCE, StageKind.RIDE, StageKind.STAY):
        stage = _stage(guide, kind)
        assert stage.state is StageState.UPCOMING and stage.party is None
        assert stage.action is FamilyAction.NOTHING_YET


def test_a_pending_party_is_named_and_the_family_has_nothing_to_do(patient):
    pending = _item(ReadinessKind.INSURANCE, ReadinessStatus.PENDING, "PM-JAY desk")

    guide = _guide(patient, items=(pending,))

    insurer = _stage(guide, StageKind.INSURANCE)
    assert insurer.state is StageState.WAITING and insurer.party == "PM-JAY desk"
    assert guide.now_stage_id == "insurance"
    assert _stage(guide, StageKind.VISIT).on is None, "a waiting party means no date"


def test_a_failed_party_is_a_problem_the_team_is_handling_and_no_date_is_promised(patient):
    blocked = _item(ReadinessKind.TRANSPORT, ReadinessStatus.BLOCKED, alternative=True,
                    detail="driver cancelled")

    guide = _guide(patient, items=(blocked,))

    ride = _stage(guide, StageKind.RIDE)
    assert ride.state is StageState.PROBLEM and ride.action is FamilyAction.WAIT_FOR_TEAM
    assert ride.detail == "driver cancelled"
    assert guide.decision == "replan"
    assert _stage(guide, StageKind.VISIT).on is None


def test_when_everyone_is_ready_the_family_gets_the_date_the_documents_and_the_first_stop(patient):
    items = (
        _item(ReadinessKind.INSURANCE, ReadinessStatus.READY, "PM-JAY desk"),
        _item(ReadinessKind.TRANSPORT, ReadinessStatus.READY, "Uber", detail="6 am pickup"),
        _item(ReadinessKind.STAY, ReadinessStatus.READY, "OYO"),
    )

    guide = _guide(patient, items=items)

    assert guide.decision == "go"
    visit = _stage(guide, StageKind.VISIT)
    assert visit.on is not None and visit.action is FamilyAction.GO_TO_FIRST_STOP
    assert visit.first_stop
    documents = _stage(guide, StageKind.DOCUMENTS)
    assert documents.action is FamilyAction.KEEP_DOCUMENTS_READY and documents.bring
    assert _stage(guide, StageKind.RIDE).action is FamilyAction.BE_READY_FOR_PICKUP
    assert guide.now_stage_id == "documents"


@pytest.mark.parametrize("status", [ReadinessStatus.PENDING, ReadinessStatus.UNKNOWN])
def test_no_date_ever_appears_unless_the_plan_is_a_go(patient, status):
    guide = _guide(patient, items=(_item(ReadinessKind.TRANSPORT, status),))

    assert guide.decision != "go"
    assert all(s.on is None and not s.bring and s.first_stop is None for s in guide.stages)


def test_a_stage_that_rests_on_a_record_cites_it(patient):
    guide = _guide(patient, items=(_item(ReadinessKind.TRANSPORT, ReadinessStatus.READY),))

    assert _stage(guide, StageKind.RIDE).evidence, "the ride's status is a ledger claim"
    assert _stage(guide, StageKind.VISIT).evidence, "so is the visit being scheduled"


def test_a_repeating_pathway_ends_with_a_next_session_that_is_never_dated():
    steps = [
        CareStep(id="D-bloods", patient_id="D", kind=StepKind.BLOODS, status=StepStatus.COMPLETED,
                 completed_on=EARLIER),
        CareStep(id="D-neph", patient_id="D", kind=StepKind.NEPHROLOGY_REVIEW,
                 status=StepStatus.COMPLETED, completed_on=EARLIER),
        CareStep(id="D-sess", patient_id="D", kind=StepKind.DIALYSIS_SESSION,
                 status=StepStatus.SCHEDULED, scheduled_for=TODAY + timedelta(days=1)),
    ]

    guide = build_guide(
        patient_id="D", pathway=DIALYSIS, steps=steps, plan=None, items=(),
        needs=(ReadinessKind.TRANSPORT,),
    )

    assert [s.kind for s in guide.stages][-1] is StageKind.NEXT_SESSION
    assert guide.stages[-1].on is None
    assert any(s.kind is StageKind.RIDE for s in guide.stages)


def test_a_visit_that_does_not_repeat_has_no_next_session(patient):
    guide = _guide(patient)

    assert StageKind.NEXT_SESSION not in {s.kind for s in guide.stages}


def test_a_family_with_no_steps_gets_an_empty_chain_not_an_error():
    guide = build_guide(
        patient_id="X", pathway=ONCOLOGY, steps=[], plan=None, items=(), needs=()
    )

    assert guide.stages == () and guide.now_stage_id is None and guide.total == 0
