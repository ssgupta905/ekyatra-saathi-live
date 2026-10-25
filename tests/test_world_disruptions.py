"""A desk's one-tap report cascades to every patient booked against the
down resource — and the family is told before any new date exists.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from saathi.bootstrap.container import build_container
from saathi.config import Settings
from saathi.domain.enums import DisruptionKind, ResourceKind, StepKind, StepStatus
from saathi.domain.models import Resource
from saathi.live.events import EventKind

START = date(2026, 11, 1)


@pytest.fixture
def state():
    settings = Settings(_env_file=None, live_watched=4)
    return build_container(settings, today=START)


def _rig_scan(state, patient_id: str, scheduled_for: date, resource_id: str = "MRI-2"):
    steps = state.world.steps[patient_id]
    for index, step in enumerate(steps):
        if step.kind is StepKind.SCAN:
            updated = step.model_copy(
                update={
                    "resource_id": resource_id,
                    "scheduled_for": scheduled_for,
                    "status": StepStatus.SCHEDULED,
                }
            )
            steps[index] = updated
            return updated
    raise AssertionError("fixture cohort has no scan step")


def test_marking_a_resource_down_affects_only_patients_booked_in_the_window(state):
    state.world.register_resource(
        Resource(id="MRI-2", kind=ResourceKind.MACHINE, display_name="MRI machine 2",
                 hospital_id="H1", department="radiology")
    )
    patients = state.world.patients()
    inside, outside = patients[0].id, patients[1].id
    _rig_scan(state, inside, START + timedelta(days=1))
    _rig_scan(state, outside, START + timedelta(days=20))

    disruption = state.world.raise_disruption(
        resource_id="MRI-2", kind=DisruptionKind.MACHINE_DOWN,
        unavailable_from=START, unavailable_to=START + timedelta(days=2),
        note="MRI-2 out of service",
    )
    affected = state.world.affected_patients(disruption)
    assert inside in affected
    assert outside not in affected


async def test_the_holding_message_is_sent_before_any_replan_event_for_that_family(state):
    state.world.register_resource(
        Resource(id="MRI-2", kind=ResourceKind.MACHINE, display_name="MRI machine 2",
                 hospital_id="H1", department="radiology")
    )
    patient_id = state.world.patients()[0].id
    _rig_scan(state, patient_id, START + timedelta(days=1))

    await state.runner.raise_disruption(
        resource_id="MRI-2", kind=DisruptionKind.MACHINE_DOWN,
        unavailable_from=START, unavailable_to=START + timedelta(days=2),
        note="MRI-2 out of service",
    )

    events = [e for e in state.bus.recent(200) if e.patient_id == patient_id]
    holding_index = next(
        i for i, e in enumerate(events) if e.kind == EventKind.HOLDING_MESSAGE_SENT
    )
    plan_index = next(
        (i for i, e in enumerate(events) if e.kind == EventKind.PLAN_RECOMPUTED), None
    )
    if plan_index is not None:
        assert holding_index < plan_index


async def test_a_disruption_fact_is_recorded_once_not_per_tick(state):
    state.world.register_resource(
        Resource(id="MRI-2", kind=ResourceKind.MACHINE, display_name="MRI machine 2",
                 hospital_id="H1", department="radiology")
    )
    patient_id = state.world.patients()[0].id
    _rig_scan(state, patient_id, START + timedelta(days=1))
    disruption = state.world.raise_disruption(
        resource_id="MRI-2", kind=DisruptionKind.MACHINE_DOWN,
        unavailable_from=START, unavailable_to=START + timedelta(days=2),
        note="MRI-2 out of service",
    )

    before = state.ledger.size()
    state.runner._record_disruption_fact(patient_id, disruption)
    once = state.ledger.size()
    state.runner._record_disruption_fact(patient_id, disruption)
    twice = state.ledger.size()

    assert once > before
    assert twice == once


async def test_an_unaffected_patients_plan_is_not_disturbed(state):
    state.world.register_resource(
        Resource(id="MRI-2", kind=ResourceKind.MACHINE, display_name="MRI machine 2",
                 hospital_id="H1", department="radiology")
    )
    patients = state.world.patients()
    affected_id, untouched_id = patients[0].id, patients[1].id
    _rig_scan(state, affected_id, START + timedelta(days=1))
    _rig_scan(state, untouched_id, START + timedelta(days=30))

    await state.runner.plan_all()
    before = state.runner.plans[untouched_id]

    await state.runner.raise_disruption(
        resource_id="MRI-2", kind=DisruptionKind.MACHINE_DOWN,
        unavailable_from=START, unavailable_to=START + timedelta(days=2),
        note="MRI-2 out of service",
    )
    after = state.runner.plans[untouched_id]
    assert before.plan == after.plan
