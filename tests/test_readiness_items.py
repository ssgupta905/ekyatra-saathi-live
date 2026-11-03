"""The other parties' answers: a ride, a slot, an insurer, a pharmacy.

A care step being done is not the same as a journey being ready. These pin the
rule that a party can only make the answer more cautious, that silence is never
readiness, and that a blocked party with another way available is a REPLAN —
a verdict that promises no date and waits for staff.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from saathi.domain.enums import (
    Decision,
    Language,
    ReadinessKind,
    ReadinessStatus,
    SourceSystem,
    StepKind,
    StepStatus,
)
from saathi.domain.models import CareStep, Patient, ReadinessItem
from saathi.main import create_app
from saathi.planner import tools
from saathi.planner.graph import VisitPlanner
from saathi.readiness.items import insurance_item, slot_item

TODAY = date(2026, 3, 10)
EARLIER = TODAY - timedelta(days=5)

READY = ReadinessStatus.READY
PENDING = ReadinessStatus.PENDING
BLOCKED = ReadinessStatus.BLOCKED
UNKNOWN = ReadinessStatus.UNKNOWN


def _item(status, *, kind=ReadinessKind.TRANSPORT, alternative=False, step_id=None, party="Uber"):
    return ReadinessItem(
        id=f"P1-{kind.value}-{party}",
        patient_id="P1",
        step_id=step_id,
        kind=kind,
        party=party,
        status=status,
        alternative_available=alternative,
        source=SourceSystem.PARTNER,
    )


# ---------------------------------------------------------------- the pure rule


@pytest.mark.parametrize(
    ("base", "items", "expected"),
    [
        (Decision.GO, [], Decision.GO),
        (Decision.GO, [_item(READY)], Decision.GO),
        (Decision.GO, [_item(PENDING)], Decision.WAIT),
        (Decision.GO, [_item(UNKNOWN)], Decision.UNCERTAIN),
        (Decision.GO, [_item(BLOCKED)], Decision.WAIT),
        (Decision.GO, [_item(BLOCKED, alternative=True)], Decision.REPLAN),
        # One blocked party with nowhere to go outweighs another that has somewhere.
        (Decision.GO, [_item(BLOCKED, alternative=True), _item(BLOCKED, party="OYO")],
         Decision.WAIT),
        # A party can only make the answer more cautious, never less.
        (Decision.WAIT, [_item(READY)], Decision.WAIT),
        (Decision.UNCERTAIN, [_item(READY)], Decision.UNCERTAIN),
        (Decision.WAIT, [_item(BLOCKED, alternative=True)], Decision.WAIT),
    ],
)
def test_a_party_can_only_make_the_answer_more_cautious(base, items, expected):
    assert tools.decide_with_items(base, items) is expected


def test_only_items_that_gate_this_visit_count():
    mine = _item(BLOCKED, step_id="S-target")
    theirs = _item(BLOCKED, step_id="S-other", party="OYO")
    next_visit = _item(READY, party="Ola")

    kept = tools.relevant_items([mine, theirs, next_visit], {"S-target"})

    assert kept == (mine, next_visit)


# ---------------------------------------------------------------- through the planner


@pytest.fixture
def patient():
    return Patient(
        id="P1",
        home_distance_km=900.0,
        home_district="Gaya",
        language=Language.HINDI,
        caregiver_phone="+919900000002",
        hospital_id="TMH-MUM",
    )


@pytest.fixture
def planner():
    return VisitPlanner(language_layer=None)


def _ready_steps():
    def done(kind):
        return CareStep(
            id=f"P1-{kind.value}", patient_id="P1", kind=kind,
            status=StepStatus.RESULT_AVAILABLE
            if kind in (StepKind.PATHOLOGY_REPORT, StepKind.RADIOLOGY_REPORT)
            else StepStatus.COMPLETED,
            completed_on=EARLIER, result_available_on=EARLIER, queue=kind.value,
        )

    steps = [done(k) for k in (
        StepKind.CONSULT, StepKind.BIOPSY, StepKind.BLOODS, StepKind.SCAN,
        StepKind.PATHOLOGY_REPORT, StepKind.RADIOLOGY_REPORT,
    )]
    steps.append(CareStep(
        id="P1-review", patient_id="P1", kind=StepKind.REVIEW_CONSULT,
        status=StepStatus.SCHEDULED, scheduled_for=TODAY + timedelta(days=2),
        queue="review_consult",
    ))
    return steps


def _plan(planner, patient, items):
    return planner.plan_visit(
        patient, _ready_steps(), StepKind.REVIEW_CONSULT, today=TODAY,
        compose=False, readiness_items=items,
    )["plan"]


def test_with_no_parties_the_plan_is_the_care_step_plan(planner, patient):
    plan = _plan(planner, patient, [])

    assert plan.decision is Decision.GO
    assert plan.readiness_items == ()


def test_a_ready_ride_leaves_a_go_plan_alone(planner, patient):
    plan = _plan(planner, patient, [_item(READY)])

    assert plan.decision is Decision.GO
    assert plan.travel_on is not None
    assert plan.what_to_bring


def test_a_cancelled_cab_with_another_available_is_a_replan_with_no_date(planner, patient):
    plan = _plan(planner, patient, [_item(BLOCKED, alternative=True)])

    assert plan.decision is Decision.REPLAN
    assert plan.travel_on is None, "a replan promises nothing"
    assert plan.what_to_bring == ()
    assert plan.where_to_go_first is None
    assert "Uber" in plan.rationale and "staff" in plan.rationale


def test_a_party_nobody_has_heard_from_means_no_date(planner, patient):
    plan = _plan(planner, patient, [_item(UNKNOWN, kind=ReadinessKind.INSURANCE, party="insurer")])

    assert plan.decision is Decision.UNCERTAIN
    assert plan.travel_on is None
    assert "insurer" in plan.rationale


def test_a_pending_pharmacy_is_a_wait_that_names_the_pharmacy(planner, patient):
    item = _item(PENDING, kind=ReadinessKind.MEDICINE, party="day-care pharmacy")

    plan = _plan(planner, patient, [item])

    assert plan.decision is Decision.WAIT
    assert "day-care pharmacy" in plan.rationale


def test_every_partys_answer_is_ledgered_with_its_source(planner, patient):
    plan = _plan(planner, patient, [_item(BLOCKED, alternative=True)])

    claims = [planner.ledger.get(ref.ledger_id) for ref in plan.evidence]
    partner = [c for c in claims if c.source is SourceSystem.PARTNER]

    assert len(partner) == 1
    assert partner[0].claim == "transport (Uber) is blocked"


def test_a_replan_is_not_a_go_for_the_message_layer(planner, patient):
    from saathi.language.rendering import plan_brief

    plan = _plan(planner, patient, [_item(BLOCKED, alternative=True)])
    brief = plan_brief(plan, planner.ledger)

    assert "DECISION: replan" in brief
    assert "Do not state or imply any date" in brief


# ---------------------------------------------------------------- the pure providers


def test_a_slot_on_a_down_machine_is_blocked_and_says_when_it_is_next_free():
    item = slot_item(
        patient_id="P1", step_id="S1", party="MRI-2", resource_up=False,
        next_free=TODAY + timedelta(days=2), alternative=True,
    )

    assert item.status is BLOCKED
    assert item.ready_by == TODAY + timedelta(days=2)
    assert item.alternative_available


def test_a_slot_nobody_has_reported_on_is_unknown_not_ready():
    assert slot_item(patient_id="P1", step_id="S1", party="MRI-2", resource_up=None).status is (
        UNKNOWN
    )


@pytest.mark.parametrize(
    ("approved", "pending", "expected"),
    [(True, False, READY), (False, False, BLOCKED), (None, True, PENDING), (None, False, UNKNOWN)],
)
def test_insurance_reads_each_answer_as_itself(approved, pending, expected):
    item = insurance_item(patient_id="P1", party="PM-JAY", approved=approved, pending=pending)

    assert item.status is expected
    assert item.kind is ReadinessKind.INSURANCE


# ---------------------------------------------------------------- over HTTP


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _a_patient_who_can_go(client):
    for board in client.get("/api/boards").json()["boards"]:
        if board["decision"] == "go":
            return board["patient"]["id"]
    pytest.skip("the demo cohort has nobody on GO today")


def test_recording_a_blocked_ride_changes_the_verdict_at_once(client):
    pid = _a_patient_who_can_go(client)

    body = client.put(
        f"/api/patients/{pid}/readiness",
        json={"kind": "transport", "party": "Uber", "status": "blocked",
              "alternative_available": True, "source": "partner"},
    ).json()

    assert body["decision"] == "replan"
    listed = client.get(f"/api/patients/{pid}/readiness").json()
    assert listed["decision"] == "replan"
    assert [i["party"] for i in listed["items"]] == ["Uber"]


def test_clearing_the_item_restores_the_verdict(client):
    pid = _a_patient_who_can_go(client)
    put = client.put(
        f"/api/patients/{pid}/readiness",
        json={"kind": "transport", "party": "Uber", "status": "blocked",
              "alternative_available": True},
    ).json()

    cleared = client.delete(f"/api/patients/{pid}/readiness/{put['item']['id']}").json()

    assert cleared["decision"] == "go"


def test_readiness_for_an_unknown_family_is_not_found(client):
    assert client.get("/api/patients/NOPE/readiness").status_code == 404
    response = client.put(
        "/api/patients/NOPE/readiness",
        json={"kind": "stay", "party": "OYO", "status": "ready"},
    )
    assert response.status_code == 404
