"""The live world must move for real reasons, and only for real reasons.

These run with no credentials and no network: the runner's actors are unset, so
what is under test is the part that must keep working when the API does not —
the clock, the release gate, the re-planning, and the scoring.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from saathi.bootstrap.container import build_container
from saathi.config import Settings
from saathi.domain.enums import Decision, StepStatus
from saathi.live.events import EventKind
from saathi.live.world import LiveWorld

START = date(2026, 9, 25)


def _world(**kwargs) -> LiveWorld:
    return LiveWorld.build(start=START, n_patients=12, **kwargs)


def _pending(world: LiveWorld) -> list:
    return [
        row
        for rows in world.steps.values()
        for row in rows
        if row.status is StepStatus.PENDING_RESULT
    ]


# ---------------------------------------------------------------- the world


def test_the_world_starts_with_reports_still_outstanding():
    """Without something pending there is nothing to watch happen."""
    world = _world()
    assert _pending(world), "no pending reports at t0 — the demo would be a still image"


def test_only_reports_whose_planted_date_has_passed_come_due():
    world = _world()
    world.clock.advance()

    for step in world.due_releases():
        truth = world.ground_truth(step.patient_id)
        assert truth.true_ready_on[step.id] <= world.today


def test_a_report_does_not_release_itself():
    """The world raises a candidate; something human-shaped has to confirm it."""
    world = _world()
    for _ in range(6):
        world.clock.advance()
    due = world.due_releases()
    assert due

    for step in due:
        world.open_candidate(step, "note", {"step_id": step.id})
    assert all(s.status is StepStatus.PENDING_RESULT for s in due), (
        "a step changed before anyone confirmed it"
    )


def test_confirming_a_candidate_is_what_releases_the_report():
    world = _world()
    for _ in range(6):
        world.clock.advance()
    step = world.due_releases()[0]
    candidate = world.open_candidate(step, "note", {"step_id": step.id})

    released = world.confirm(candidate.id)
    assert released is not None
    assert released.status is StepStatus.RESULT_AVAILABLE
    assert released.result_available_on == world.today
    assert world.step(step.id).status is StepStatus.RESULT_AVAILABLE


def test_a_candidate_is_only_confirmed_once():
    world = _world()
    for _ in range(6):
        world.clock.advance()
    step = world.due_releases()[0]
    candidate = world.open_candidate(step, "note", {"step_id": step.id})

    assert world.confirm(candidate.id) is not None
    assert world.confirm(candidate.id) is None


def test_the_same_step_is_not_queued_twice():
    world = _world()
    for _ in range(6):
        world.clock.advance()
    step = world.due_releases()[0]
    world.open_candidate(step, "note", {"step_id": step.id})

    assert step.id not in {s.id for s in world.due_releases()}


def test_candidates_age_towards_an_automatic_confirmation():
    world = _world(auto_confirm_ticks=2)
    for _ in range(6):
        world.clock.advance()
    step = world.due_releases()[0]
    world.open_candidate(step, "note", {"step_id": step.id})

    assert world.age_candidates() == []
    expired = world.age_candidates()
    assert [c.step_id for c in expired] == [step.id]


def test_reset_is_deterministic():
    """A demo that cannot be run twice is a demo you cannot rehearse."""
    world = _world()
    for _ in range(8):
        world.clock.advance()
        for step in world.due_releases():
            world.confirm(world.open_candidate(step, "n", {}).id)
    moved = world.pending_report_count()

    world.reset()
    assert world.today == START
    assert world.pending_report_count() >= moved
    assert world.pending_report_count() == _world().pending_report_count()


def test_ground_truth_is_never_handed_to_the_planner():
    """The planner must work the timing out, not be told it."""
    world = _world()
    planner_inputs = world.steps_for(world.patients()[0].id)
    assert all(not hasattr(step, "true_ready_on") for step in planner_inputs)
    truth = world.ground_truth(world.patients()[0].id)
    assert truth.true_ready_on, "the test cohort has no planted truth to leak"


# ---------------------------------------------------------------- the runner


@pytest.fixture
def state():
    settings = Settings(_env_file=None, live_watched=4)
    return build_container(settings, today=START)


async def test_a_tick_replans_every_patient(state):
    runner = state.runner
    await runner.plan_all()
    assert len(runner.plans) == len(state.world.patients())
    assert all(run.plan is not None for run in runner.plans.values())


async def test_a_release_flips_the_answer_and_says_so(state):
    """The one moment the whole demo exists to show: WAIT becomes GO because a
    report landed, and the event stream carries the real cost of working it out."""
    runner, world = state.runner, state.world
    await runner.plan_all()

    waiting = [
        pid
        for pid, run in runner.plans.items()
        if run.decision is Decision.WAIT and len(run.plan.blocked_by) == 1
    ]
    assert waiting, "no singly-blocked family to advance"
    patient_id = waiting[0]
    blocked_step = runner.plans[patient_id].plan.blocked_by[0].step_id

    # Move the clock past this family's planted ready date and release it.
    truth = world.ground_truth(patient_id)
    while world.today < truth.true_ready_on[blocked_step]:
        world.clock.advance()
    step = world.step(blocked_step)
    candidate = world.open_candidate(step, "released", {"step_id": step.id})
    await runner.confirm(candidate.id)

    run = runner.plans[patient_id]
    assert run.decision is Decision.GO
    assert run.previous_decision is Decision.WAIT
    assert run.plan.travel_on is not None

    kinds = [e.kind for e in state.bus.recent(50)]
    assert EventKind.STEP_RELEASED in kinds
    assert EventKind.PLAN_RECOMPUTED in kinds

    timed = [e for e in state.bus.recent(50) if e.duration_ms is not None]
    assert timed, "no event carried a measured duration"
    assert all(e.duration_ms > 0 for e in timed)


async def test_replanning_an_unchanged_patient_does_not_grow_the_ledger(state):
    runner = state.runner
    await runner.plan_all()
    size = state.ledger.size()
    await runner.plan_all()
    assert state.ledger.size() == size
    assert state.ledger.verify()


async def test_metrics_are_scored_against_planted_truth(state):
    runner = state.runner
    await runner.plan_all()
    await runner.update_metrics()
    assert runner.metrics["patients"] == len(state.world.patients())
    assert runner.metrics["saathi_wasted_trips"] <= runner.metrics["baseline_wasted_trips"]


async def test_the_world_ticks_with_no_language_layer_and_no_actors(state):
    """The degraded path is the one CI runs, and it must be the full decision path."""
    assert state.planner.language_layer is None
    assert state.runner.actors is None

    await state.runner.tick()
    assert state.world.today == START + timedelta(days=1)
    assert all(run.plan is not None for run in state.runner.plans.values())
    assert state.ledger.verify()


async def test_an_inbound_clinical_question_raises_a_real_alert(state):
    """Typed by a person rather than written by an actor — the guard cannot tell."""
    patient_id = state.world.patients()[0].id
    record = await state.runner.receive_inbound(
        patient_id, text="report mein kya aaya, kya ye cancer hai?"
    )
    assert record is not None
    assert record.answerable is False
    assert record.triggers
    assert len(state.alerts) == 1

    kinds = [e.kind for e in state.bus.recent(20)]
    assert EventKind.GUARD_BLOCKED in kinds
    assert EventKind.ALERT_RAISED in kinds


async def test_an_inbound_logistics_question_is_answerable(state):
    patient_id = state.world.patients()[0].id
    record = await state.runner.receive_inbound(
        patient_id, text="train ka kiraya kitna lagega aur kab aana hai?"
    )
    assert record.answerable is True
    assert state.alerts == []


async def test_an_actorless_runner_produces_no_message_of_its_own(state):
    """With no actors, nothing invents a caregiver message."""
    patient_id = state.world.patients()[0].id
    assert await state.runner.receive_inbound(patient_id) is None


async def test_a_moved_travel_date_invalidates_the_cached_message(state):
    """A GO message naming last week's date is the one error that costs a trip.

    Found live: the planner recomputes a GO plan's travel date from the current
    day, so the date slides forward without the *decision* changing. Keying
    message invalidation on the decision alone left families looking at a date
    that had moved.
    """
    runner, world = state.runner, state.world
    await runner.plan_all()

    going = [pid for pid, run in runner.plans.items() if run.decision is Decision.GO]
    assert going, "no GO family in this cohort to advance"
    patient_id = going[0]

    before = runner.plans[patient_id].plan.travel_on
    # Stand in for a rendered message; the layer is off in this configuration.
    runner.plans[patient_id].message = object()
    runner.plans[patient_id].rendered_by = "stub"

    world.clock.advance()
    await runner.plan_all()

    run = runner.plans[patient_id]
    assert run.plan.travel_on != before, "the travel date did not move"
    assert run.decision is Decision.GO, "the decision should not have changed"
    assert run.plan_changed is True
    assert run.message is None, "a message about the old date survived the move"
    assert run.rendered_by is None


async def test_an_unchanged_plan_keeps_its_message(state):
    """The flip side: re-planning an unchanged family must not churn the model."""
    runner = state.runner
    await runner.plan_all()

    waiting = [pid for pid, run in runner.plans.items() if run.decision is Decision.WAIT]
    assert waiting
    patient_id = waiting[0]
    sentinel = object()
    runner.plans[patient_id].message = sentinel

    await runner.plan_all()

    assert runner.plans[patient_id].plan_changed is False
    assert runner.plans[patient_id].message is sentinel
