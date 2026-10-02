"""The actors are allowed to be wrong. They are not allowed to be believed.

Each one produces an input or a reading, never a decision, so what matters is
not that the model behaves — it is that the code around it refuses output it
cannot check. These tests stub the transport and feed each actor the worst
plausible thing it could return.
"""

from __future__ import annotations

from datetime import date

import pytest
from saathi.domain.enums import Decision, Language, SourceSystem, StepKind, StepStatus
from saathi.domain.models import CareStep, Patient, VisitPlan
from saathi.ledger.evidence import InMemoryEvidenceLedger
from saathi.live.actors import GroqActors
from saathi.live.world import LiveWorld

START = date(2026, 9, 25)


class _Run:
    """Stands in for a `PlanRun` — the actors only read `.plan` off it."""

    def __init__(self, plan):
        self.plan = plan


@pytest.fixture
def world() -> LiveWorld:
    return LiveWorld.build(start=START, n_patients=4)


@pytest.fixture
def actors(world) -> GroqActors:
    return GroqActors(api_key="test-key-not-used", world=world)


def _answer(actors: GroqActors, payload):
    """Replace the transport. Every actor goes through `_json`."""

    async def _json(system, prompt, response_format, temperature=0.6):
        return payload

    actors._json = _json  # type: ignore[method-assign]


@pytest.fixture
def ledger_and_plan():
    ledger = InMemoryEvidenceLedger()
    entry = ledger.record(
        patient_id="P0000",
        source=SourceSystem.ABDM,
        source_record_id="P0000-pathology_report",
        claim="pathology_report is pending_result",
    )
    plan = VisitPlan(
        patient_id="P0000",
        target_step_id="P0000-review",
        decision=Decision.WAIT,
        evidence=(entry.ref(),),
    )
    return ledger, entry, plan


# ---------------------------------------------------------------- ward notes


async def test_a_drafted_note_that_mentions_findings_is_discarded(actors, world):
    """A release log records that a report exists, never what it found."""
    _answer(actors, {"note": "Path report released. Biopsy said malignant, grade 3."})
    step = world.step("P0000-pathology_report")

    assert await actors.draft_ward_note(step, world.today) is None


async def test_a_clean_note_is_kept(actors, world):
    _answer(actors, {"note": "Path rpt P0000 released 25/09, slides filed."})
    step = world.step("P0000-pathology_report")

    assert "released" in (await actors.draft_ward_note(step, world.today))


# ---------------------------------------------------------------- parsing


async def test_a_parse_naming_an_unknown_step_is_rejected(actors):
    """A desk clerk should be confirming a record, not a hallucination."""
    _answer(
        actors,
        {
            "step_id": "P9999-pathology_report",
            "new_status": "result_available",
            "released_on": "2026-09-25",
            "confidence": "high",
        },
    )
    assert await actors.parse_ward_note("note", "P0000-pathology_report") is None


async def test_a_parse_with_a_status_outside_the_vocabulary_is_rejected(actors):
    _answer(
        actors,
        {
            "step_id": "P0000-pathology_report",
            "new_status": "looks_fine",
            "released_on": "2026-09-25",
            "confidence": "high",
        },
    )
    assert await actors.parse_ward_note("note", "P0000-pathology_report") is None


async def test_a_parse_that_names_a_different_real_step_is_flagged_not_hidden(actors):
    """The mismatch is for the reviewer to see, which means surfacing it."""
    _answer(
        actors,
        {
            "step_id": "P0001-pathology_report",
            "new_status": "result_available",
            "released_on": "2026-09-25",
            "confidence": "low",
        },
    )
    parsed = await actors.parse_ward_note("note", "P0000-pathology_report")

    assert parsed is not None
    assert parsed["matches_expected"] is False
    assert parsed["step_id"] == "P0001-pathology_report"


async def test_an_unreadable_date_falls_back_to_today_rather_than_failing(actors, world):
    _answer(
        actors,
        {
            "step_id": "P0000-pathology_report",
            "new_status": StepStatus.RESULT_AVAILABLE.value,
            "released_on": "sometime last week",
            "confidence": "low",
        },
    )
    parsed = await actors.parse_ward_note("note", "P0000-pathology_report")
    assert parsed["released_on"] == world.today.isoformat()


# ---------------------------------------------------------------- the brief


async def test_brief_lines_without_a_resolvable_citation_are_dropped(
    actors, ledger_and_plan
):
    """Every chip on the brief has to open a real row."""
    ledger, entry, plan = ledger_and_plan
    _answer(
        actors,
        {
            "lines": [
                {"text": "Report still outstanding.", "ledger_ids": [entry.id]},
                {"text": "Family called twice on Tuesday.", "ledger_ids": ["made-up-id"]},
                {"text": "No citation at all.", "ledger_ids": []},
            ]
        },
    )
    patient = Patient(
        id="P0000",
        home_distance_km=1800.0,
        home_district="Darbhanga",
        language=Language.HINDI,
        caregiver_phone="+910000000000",
        hospital_id="TMH-MUM",
    )
    lines = await actors.call_prep_brief(
        patient=patient,
        plan_run=_Run(plan),
        steps=[],
        ledger=ledger,
        alerts=[],
        inbound=[],
    )
    assert [line["text"] for line in lines] == ["Report still outstanding."]


async def test_a_clinical_brief_line_is_dropped(actors, ledger_and_plan):
    ledger, entry, plan = ledger_and_plan
    _answer(
        actors,
        {"lines": [{"text": "Biopsy suggests malignancy.", "ledger_ids": [entry.id]}]},
    )
    patient = Patient(
        id="P0000",
        home_distance_km=1800.0,
        home_district="Darbhanga",
        language=Language.HINDI,
        caregiver_phone="+910000000000",
        hospital_id="TMH-MUM",
    )
    lines = await actors.call_prep_brief(
        patient=patient, plan_run=_Run(plan), steps=[], ledger=ledger, alerts=[], inbound=[]
    )
    assert lines == []


# ---------------------------------------------------------------- narration


async def test_a_narrated_line_that_fails_the_guard_comes_back_held(
    actors, ledger_and_plan
):
    """Held, not dropped — the navigator needs to know a line is missing."""
    ledger, _entry, plan = ledger_and_plan
    _answer(
        actors,
        {
            "nodes": [
                {"id": "gate", "text": "Report abhi nahi aayi hai."},
                {"id": "verdict", "text": "Aap aaiye, chinta mat kijiye."},
            ]
        },
    )
    patient = Patient(
        id="P0000",
        home_distance_km=1800.0,
        home_district="Darbhanga",
        language=Language.HINDI,
        caregiver_phone="+910000000000",
        hospital_id="TMH-MUM",
    )
    nodes = await actors.narrate_trace(
        nodes=[{"id": "gate", "text": "..."}, {"id": "verdict", "text": "..."}],
        patient=patient,
        plan_run=_Run(plan),
        ledger=ledger,
    )
    by_id = {n["id"]: n for n in nodes}
    assert by_id["gate"]["held"] is False
    assert by_id["verdict"]["held"] is True
    assert by_id["verdict"]["text"] == ""


async def test_narration_ignores_nodes_the_console_did_not_ask_for(
    actors, ledger_and_plan
):
    ledger, _entry, plan = ledger_and_plan
    _answer(actors, {"nodes": [{"id": "smuggled", "text": "Extra line."}]})
    patient = Patient(
        id="P0000",
        home_distance_km=1800.0,
        home_district="Darbhanga",
        language=Language.HINDI,
        caregiver_phone="+910000000000",
        hospital_id="TMH-MUM",
    )
    nodes = await actors.narrate_trace(
        nodes=[{"id": "gate", "text": "..."}],
        patient=patient,
        plan_run=_Run(plan),
        ledger=ledger,
    )
    assert nodes == []


# ---------------------------------------------------------------- failure


async def test_every_actor_returns_none_when_the_api_does_not_answer(actors, world):
    """A failed call must never raise into the tick loop."""
    _answer(actors, None)
    patient = Patient(
        id="P0000",
        home_distance_km=1800.0,
        home_district="Darbhanga",
        language=Language.HINDI,
        caregiver_phone="+910000000000",
        hospital_id="TMH-MUM",
    )
    step = CareStep(
        id="P0000-pathology_report",
        patient_id="P0000",
        kind=StepKind.PATHOLOGY_REPORT,
        status=StepStatus.PENDING_RESULT,
        queue="pathology_report",
    )

    assert await actors.draft_ward_note(step, world.today) is None
    assert await actors.parse_ward_note("note", step.id) is None
    assert await actors.write_caregiver_message(patient, None) is None
    assert (
        await actors.call_prep_brief(
            patient=patient,
            plan_run=None,
            steps=[],
            ledger=InMemoryEvidenceLedger(),
            alerts=[],
            inbound=[],
        )
    ) == []
