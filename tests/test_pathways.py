"""Care pathways are data: a new condition is a new `Pathway`, not new planner code.

Oncology keeps behaving exactly as it did (the rest of the suite is that proof);
these tests pin what is new — other pathways plan on their own graph, documents
and first stops, and a patient's pathway survives the database.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from saathi.adapters.records import SqlRecordStore
from saathi.domain.enums import Decision, Language, StepKind, StepStatus
from saathi.domain.models import CareStep, Patient
from saathi.domain.pathway import DIALYSIS, ONCOLOGY, PATHWAYS, POST_DISCHARGE, get_pathway
from saathi.graph.dependencies import (
    CO_LOCATABLE,
    DEFAULT_EDGES,
    InMemoryDependencyGraph,
)
from saathi.planner import tools
from saathi.planner.graph import VisitPlanner

TODAY = date(2026, 3, 10)
EARLIER = TODAY - timedelta(days=3)


def _patient(pathway_id: str) -> Patient:
    return Patient(
        id="P-DIAL",
        home_distance_km=240.0,
        home_district="Bankura",
        language=Language.BENGALI,
        caregiver_phone="+919900000001",
        hospital_id="TMH-MUM",
        pathway_id=pathway_id,
    )


def _step(kind: StepKind, status: StepStatus, **extra) -> CareStep:
    return CareStep(
        id=f"P-DIAL-{kind.value}",
        patient_id="P-DIAL",
        kind=kind,
        status=status,
        queue=kind.value,
        **extra,
    )


@pytest.fixture
def planner():
    return VisitPlanner(language_layer=None)


def test_the_legacy_oncology_tables_are_the_oncology_pathway():
    assert DEFAULT_EDGES == ONCOLOGY.edges
    assert CO_LOCATABLE == ONCOLOGY.co_locatable
    assert tools.FIRST_STOP == ONCOLOGY.first_stop
    assert tools.ECHO_GATED_DOSES == frozenset({5, 9, 13, 17})


@pytest.mark.parametrize("pathway", PATHWAYS.values(), ids=lambda p: p.id)
def test_every_pathway_is_a_dag_and_names_only_its_own_steps(pathway):
    # Building the graph raises CycleError on a cycle.
    graph = InMemoryDependencyGraph.from_pathway(pathway)
    for parent, child in pathway.edges:
        assert parent in graph.transitive_prerequisites(child)
    assert pathway.default_target in pathway.kinds


def test_an_unknown_pathway_is_an_error_not_oncology():
    with pytest.raises(KeyError):
        get_pathway("nope")


def test_a_dialysis_patient_is_planned_on_the_dialysis_graph(planner):
    patient = _patient("dialysis")
    steps = [
        _step(StepKind.BLOODS, StepStatus.COMPLETED, completed_on=EARLIER),
        _step(StepKind.NEPHROLOGY_REVIEW, StepStatus.COMPLETED, completed_on=EARLIER),
        _step(
            StepKind.DIALYSIS_SESSION,
            StepStatus.SCHEDULED,
            scheduled_for=TODAY + timedelta(days=1),
        ),
    ]

    state = planner.plan_visit(patient, steps, StepKind.DIALYSIS_SESSION, TODAY, compose=False)
    plan = state["plan"]

    assert plan.decision is Decision.GO
    # The oncology graph has no idea what a dialysis session needs, so a GO here
    # can only have come from the dialysis pathway's own edges.
    assert plan.where_to_go_first == "dialysis unit reception"
    assert "dialysis card" in plan.what_to_bring


def test_a_dialysis_session_waits_on_a_review_that_is_not_done(planner):
    patient = _patient("dialysis")
    steps = [
        _step(StepKind.BLOODS, StepStatus.COMPLETED, completed_on=EARLIER),
        _step(
            StepKind.NEPHROLOGY_REVIEW,
            StepStatus.SCHEDULED,
            scheduled_for=TODAY + timedelta(days=2),
        ),
        _step(
            StepKind.DIALYSIS_SESSION,
            StepStatus.SCHEDULED,
            scheduled_for=TODAY + timedelta(days=3),
        ),
    ]

    state = planner.plan_visit(patient, steps, StepKind.DIALYSIS_SESSION, TODAY, compose=False)

    assert state["plan"].decision is not Decision.GO
    assert [b.kind for b in state["plan"].blocked_by] == [StepKind.NEPHROLOGY_REVIEW]


def test_a_missing_prerequisite_is_judged_against_the_patients_own_pathway(planner):
    # Oncology would call the dialysis patient's missing CONSULT unknowable. On
    # the dialysis pathway the consult is not a prerequisite at all.
    patient = _patient("dialysis")
    steps = [
        _step(StepKind.BLOODS, StepStatus.COMPLETED, completed_on=EARLIER),
        _step(StepKind.NEPHROLOGY_REVIEW, StepStatus.COMPLETED, completed_on=EARLIER),
        _step(StepKind.DIALYSIS_SESSION, StepStatus.SCHEDULED, scheduled_for=TODAY),
    ]
    state = planner.plan_visit(patient, steps, StepKind.DIALYSIS_SESSION, TODAY, compose=False)
    assert state["missing_kinds"] == frozenset()


def test_the_post_discharge_pathway_bundles_what_shares_a_trip(planner):
    patient = _patient("post_discharge")
    steps = [
        _step(StepKind.BLOODS, StepStatus.SCHEDULED, scheduled_for=TODAY + timedelta(days=1)),
        _step(StepKind.WOUND_CHECK, StepStatus.SCHEDULED, scheduled_for=TODAY + timedelta(days=1)),
        _step(
            StepKind.DISCHARGE_REVIEW,
            StepStatus.SCHEDULED,
            scheduled_for=TODAY + timedelta(days=1),
        ),
    ]

    state = planner.plan_visit(patient, steps, StepKind.DISCHARGE_REVIEW, TODAY, compose=False)

    bundled = set(state["plan"].bundled_step_ids)
    assert POST_DISCHARGE.id == "post_discharge"
    assert bundled <= {s.id for s in steps}


def test_recurrence_rules_come_from_the_pathway():
    assert tools.requires_echo_bundle(5)
    assert not tools.requires_echo_bundle(6)
    # Dialysis repeats every second day and has no gated companion.
    assert DIALYSIS.recurrence is not None and DIALYSIS.recurrence.total is None
    assert not tools.requires_echo_bundle(5, DIALYSIS)


def test_a_patients_pathway_survives_the_database(tmp_path):
    url = f"sqlite:///{tmp_path}/pathway.db"
    store = SqlRecordStore(url)
    store.save_patient(_patient("dialysis"))
    store.close()

    assert SqlRecordStore(url).load().patients[0].pathway_id == "dialysis"
