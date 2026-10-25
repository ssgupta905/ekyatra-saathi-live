"""The single approval action: role-gated, fans out, and is itself logged."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from saathi.bootstrap.container import build_container
from saathi.config import Settings
from saathi.domain.enums import DisruptionKind, ResourceKind, Role, StepKind, StepStatus
from saathi.domain.models import Resource
from saathi.live.events import EventKind

START = date(2026, 11, 13)


@pytest.fixture
def state():
    settings = Settings(_env_file=None, live_watched=4)
    return build_container(settings, today=START)


def _rig_long_delay(state, patient_id: str) -> None:
    """A disruption whose delay is long enough to force a real choice."""
    steps = state.world.steps[patient_id]
    for index, step in enumerate(steps):
        if step.kind is StepKind.SCAN:
            steps[index] = step.model_copy(
                update={
                    "resource_id": "MRI-2",
                    "scheduled_for": START + timedelta(days=1),
                    "status": StepStatus.SCHEDULED,
                }
            )
    state.world.register_resource(
        Resource(id="MRI-2", kind=ResourceKind.MACHINE, display_name="MRI machine 2",
                 hospital_id="H1", department="radiology")
    )


async def _raise_and_get_options(state, patient_id):
    await state.runner.raise_disruption(
        resource_id="MRI-2", kind=DisruptionKind.MACHINE_DOWN,
        unavailable_from=START, unavailable_to=START + timedelta(days=10),
        note="MRI-2 out of service",
    )
    return state.runner.options.get(patient_id)


async def test_a_navigator_may_approve_a_scan_level_option(state):
    patient_id = state.world.patients()[0].id
    _rig_long_delay(state, patient_id)
    option_set = await _raise_and_get_options(state, patient_id)
    assert option_set is not None, "fixture did not produce a human-choice case"

    approval = await state.runner.approve_option(
        patient_id=patient_id, option_index=0,
        approved_by_role=Role.NAVIGATOR, approved_by="Seema Kamble",
    )
    assert approval.approved_by_role is Role.NAVIGATOR
    assert patient_id not in state.runner.options


async def test_a_navigator_cannot_approve_a_treatment_touching_option(state):
    patient_id = state.world.patients()[0].id
    _rig_long_delay(state, patient_id)
    option_set = await _raise_and_get_options(state, patient_id)
    assert option_set is not None

    # Force the target step to look like it touches treatment.
    step = state.world.step(option_set.options[0].target_step_id)
    for rows in state.world.steps.values():
        for i, s in enumerate(rows):
            if s.id == step.id:
                rows[i] = s.model_copy(update={"kind": StepKind.TREATMENT})

    with pytest.raises(PermissionError):
        await state.runner.approve_option(
            patient_id=patient_id, option_index=0,
            approved_by_role=Role.NAVIGATOR, approved_by="Seema Kamble",
        )


async def test_approving_is_itself_a_ledger_entry(state):
    patient_id = state.world.patients()[0].id
    _rig_long_delay(state, patient_id)
    await _raise_and_get_options(state, patient_id)
    before = state.ledger.size()

    await state.runner.approve_option(
        patient_id=patient_id, option_index=0,
        approved_by_role=Role.NAVIGATOR, approved_by="Seema Kamble",
    )
    assert state.ledger.size() > before
    assert state.ledger.verify()


async def test_approving_publishes_an_approval_event(state):
    patient_id = state.world.patients()[0].id
    _rig_long_delay(state, patient_id)
    await _raise_and_get_options(state, patient_id)

    await state.runner.approve_option(
        patient_id=patient_id, option_index=0,
        approved_by_role=Role.NAVIGATOR, approved_by="Seema Kamble",
    )
    kinds = [e.kind for e in state.bus.recent(200) if e.patient_id == patient_id]
    assert EventKind.APPROVAL_RECORDED in kinds


async def test_an_ivr_press_one_is_logged_as_a_confirmation(state):
    patient_id = state.world.patients()[0].id
    confirmation = state.runner._open_ivr_confirmation(patient_id, "test message")
    before = state.ledger.size()

    ok = await state.runner.confirm_ivr(confirmation.id, "1")
    assert ok
    assert state.ledger.size() > before
    kinds = [e.kind for e in state.bus.recent(50)]
    assert EventKind.CONFIRMATION_RECEIVED in kinds


async def test_an_already_confirmed_ivr_cannot_be_confirmed_twice(state):
    patient_id = state.world.patients()[0].id
    confirmation = state.runner._open_ivr_confirmation(patient_id, "test message")
    assert await state.runner.confirm_ivr(confirmation.id, "1")
    assert not await state.runner.confirm_ivr(confirmation.id, "1")


def test_an_option_converts_to_a_plan_whatever_fields_it_grows():
    """The conversion must not depend on a hand-maintained list of differences.

    It did, and the list rotted: adding `PlanOption.target_on` made approving an
    option raise `extra_forbidden`, which surfaced only as a story that stopped
    advancing one beat early.
    """
    from saathi.domain.models import PlanOption, VisitPlan

    option_only = set(PlanOption.model_fields) - set(VisitPlan.model_fields)
    shared = set(PlanOption.model_fields) & set(VisitPlan.model_fields)

    assert shared, "a PlanOption should still be shaped like the plan it becomes"
    # Every field a VisitPlan requires must be available on the option.
    required = {
        name for name, f in VisitPlan.model_fields.items() if f.is_required()
    }
    assert required <= set(PlanOption.model_fields)
    # And the difference is exactly what gets excluded, by construction.
    assert "target_on" in option_only
