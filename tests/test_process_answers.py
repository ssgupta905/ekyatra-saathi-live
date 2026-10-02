"""A process-only question gets a process-only answer, never a clinical one —
even while a decision is still pending, and even when the question is
clinically phrased.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from saathi.api.deps import build_state
from saathi.config import Settings
from saathi.domain.enums import DisruptionKind, ResourceKind, StepKind, StepStatus
from saathi.domain.models import Resource
from saathi.language import guard
from saathi.language.guard import InboundCategory
from saathi.live.events import EventKind
from saathi.planner.process_facts import resolve_process_fact

START = date(2026, 11, 17)


@pytest.fixture
def state():
    settings = Settings(_env_file=None, live_watched=4)
    return build_state(settings, today=START)


def _rig_and_disrupt(state, patient_id: str) -> None:
    steps = state.world.steps[patient_id]
    for index, step in enumerate(steps):
        if step.kind is StepKind.SCAN:
            steps[index] = step.model_copy(
                update={"resource_id": "MRI-2", "scheduled_for": START + timedelta(days=1),
                        "status": StepStatus.SCHEDULED}
            )
    state.world.register_resource(
        Resource(id="MRI-2", kind=ResourceKind.MACHINE, display_name="MRI machine 2",
                 hospital_id="H1", department="radiology")
    )


def test_classify_inbound_separates_process_from_clinical_from_other():
    assert guard.classify_inbound("what happens to my dose 13") == InboundCategory.PROCESS
    clinical = guard.classify_inbound("is it cancer, what does the report say")
    assert clinical == InboundCategory.CLINICAL
    assert guard.classify_inbound("train ka kiraya kitna hai") == InboundCategory.OTHER


def test_a_clinically_phrased_process_question_is_still_routed_as_clinical():
    """"what happens to" a clinical topic must not slip past as process."""
    assert guard.classify_inbound("what happens to my diagnosis now") == InboundCategory.CLINICAL


def test_a_dose_number_does_not_trip_the_generic_dose_clinical_term():
    """"dose 13" names a cycle, not a clinical amount — the maintenance story
    depends on this distinction to ever reach a process answer at all."""
    assert guard.classify_inbound("what happens to dose 13") == InboundCategory.PROCESS


async def test_resolve_process_fact_is_none_with_no_open_disruption(state):
    patient_id = state.world.patients()[0].id
    assert resolve_process_fact(patient_id, state.world) is None


async def test_resolve_process_fact_names_who_decides_once_a_disruption_is_open(state):
    patient_id = state.world.patients()[0].id
    _rig_and_disrupt(state, patient_id)
    await state.runner.raise_disruption(
        resource_id="MRI-2", kind=DisruptionKind.MACHINE_DOWN,
        unavailable_from=START, unavailable_to=START + timedelta(days=10),
        note="MRI-2 out of service",
    )
    fact = resolve_process_fact(patient_id, state.world)
    assert fact is not None
    assert fact.awaiting


async def test_an_inbound_process_question_gets_answered_not_just_alerted(state):
    patient_id = state.world.patients()[0].id
    _rig_and_disrupt(state, patient_id)
    await state.runner.raise_disruption(
        resource_id="MRI-2", kind=DisruptionKind.MACHINE_DOWN,
        unavailable_from=START, unavailable_to=START + timedelta(days=10),
        note="MRI-2 out of service",
    )
    alerts_before = len(state.alerts)

    record = await state.runner.receive_inbound(
        patient_id, text="what happens to my scan now"
    )
    assert record.answerable is True
    assert len(state.alerts) == alerts_before, "a process question must not raise a clinical alert"

    kinds = [e.kind for e in state.bus.recent(50) if e.patient_id == patient_id]
    assert EventKind.PROCESS_ANSWERED in kinds


async def test_a_clinical_question_is_still_never_answered(state):
    patient_id = state.world.patients()[0].id
    _rig_and_disrupt(state, patient_id)
    await state.runner.raise_disruption(
        resource_id="MRI-2", kind=DisruptionKind.MACHINE_DOWN,
        unavailable_from=START, unavailable_to=START + timedelta(days=10),
        note="MRI-2 out of service",
    )
    record = await state.runner.receive_inbound(
        patient_id, text="is it cancer, what does the report say"
    )
    assert record.answerable is False
    kinds = [e.kind for e in state.bus.recent(50) if e.patient_id == patient_id]
    assert EventKind.PROCESS_ANSWERED not in kinds
