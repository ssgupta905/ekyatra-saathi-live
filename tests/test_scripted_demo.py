"""The two brief-scripted families: seeding, and the "press advance" loop
driving them through real disruptions and real approvals.
"""

from __future__ import annotations

from datetime import date

import pytest
from saathi.api.deps import build_state
from saathi.config import Settings
from saathi.domain.enums import StepKind
from saathi.live.events import EventKind
from saathi.synthetic.scripted import ANITA_ID, SHAMBHU_ID, seed_anita_devi, seed_shambhu_prasad

START = date(2026, 11, 12)


def test_shambhu_prasad_has_an_mri_booked_against_a_named_resource():
    patient, steps, truth = seed_shambhu_prasad(START)
    scan = next(s for s in steps if s.kind is StepKind.SCAN)
    assert scan.resource_id == "MRI-2"
    assert patient.id == SHAMBHU_ID


def test_anita_devi_sits_at_an_echo_gated_dose():
    patient, steps, truth, cycle = seed_anita_devi(START)
    assert cycle.dose_index == 13
    assert cycle.requires_echo
    dose = next(s for s in steps if s.kind is StepKind.MAINTENANCE_DOSE)
    echo = next(s for s in steps if s.kind is StepKind.ECHO_REVIEW)
    assert dose.resource_id and echo.resource_id


@pytest.fixture
def scripted_state():
    settings = Settings(_env_file=None, live_watched=4, live_scripted=True)
    return build_state(settings, today=START)


async def test_the_scripted_world_plans_both_families_from_the_start(scripted_state):
    runner = scripted_state.runner
    await runner.plan_all()
    assert SHAMBHU_ID in runner.plans
    assert ANITA_ID in runner.plans
    assert SHAMBHU_ID in scripted_state.world.watched
    assert ANITA_ID in scripted_state.world.watched


async def test_advancing_shambhus_story_raises_a_disruption_then_approves(scripted_state):
    runner = scripted_state.runner
    await runner.plan_all()

    first = await runner.advance_story("shambhu")
    assert first["beat"] == "disrupt"
    kinds = [e.kind for e in scripted_state.bus.recent(200)]
    assert EventKind.DISRUPTION_RAISED in kinds
    assert EventKind.HOLDING_MESSAGE_SENT in kinds

    second = await runner.advance_story("shambhu")
    assert second["beat"] == "approve_first_option"
    assert second["done"] is True


async def test_advancing_anitas_story_fires_the_echo_gate_exactly_at_dose_13(scripted_state):
    runner = scripted_state.runner
    await runner.plan_all()

    for _ in range(4):
        await runner.advance_story("anita")

    approvals = [a for a in runner.approvals if a.patient_id == ANITA_ID]
    assert len(approvals) == 2
    for approval in approvals:
        step = scripted_state.world.step(approval.option_summary.target_step_id)
        is_dose_go = (
            step is not None
            and step.kind is StepKind.MAINTENANCE_DOSE
            and approval.option_summary.decision.value == "go"
        )
        if is_dose_go:
            assert any(
                sid.endswith("-echo_review") for sid in approval.option_summary.bundled_step_ids
            ), "dose 13 was approved without its echo bundled"


async def test_an_unknown_story_is_rejected(scripted_state):
    with pytest.raises(LookupError):
        await scripted_state.runner.advance_story("nope")
