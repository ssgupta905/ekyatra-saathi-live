"""A confirmed reading has to actually drive a search.

This closes a gap that was invisible from the outside and total on the
inside. `extract_request` read what a family said. A navigator agreed with
the reading. `candidates_for_request` — which exists, is tested, and knows
how to try what was asked for, the edge of the hospital's tolerance, and
*earlier* — had **no callers at all** outside its own tests. So the whole
chain ran, the constraint was confirmed, and then the re-plan was computed by
a planner that had never heard of it.

The two things pinned here are the wiring and its refusal. A hospital with no
saved rules has stated no tolerance and no slot calendar, so there is nothing
to search inside; searching anyway would mean inventing both, and a date this
system made up is the one thing it must never put in front of a family.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from saathi.domain.policy import StepPolicy, default_policy
from saathi.domain.requests import PatientRequest, RequestConstraint, RequestIntent
from saathi.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _reading(patient_id: str, **constraint) -> PatientRequest:
    return PatientRequest(
        id="r-test-1",
        patient_id=patient_id,
        raw_text="(what the family said)",
        intent=RequestIntent.MOVE_VISIT,
        constraint=RequestConstraint(**constraint),
        confirmed_by="Seema Kamble",
    )


async def test_no_saved_rules_means_no_search_and_no_invented_date(client) -> None:
    """The refusal, which matters more than the happy path.

    If this ever starts returning a search, the planner has begun inventing a
    tolerance the hospital never stated.
    """
    runner = client.app.state.container.runner
    patient = client.app.state.container.world.patients()[0]
    runner.planner.rules_for = lambda _hospital_id: None

    search = await runner.replan_for_request(patient.id, _reading(patient.id))

    assert search is None
    assert patient.id not in runner.searches
    assert patient.id not in runner.options, "options were offered with no rules behind them"


async def test_a_reading_with_nothing_to_act_on_searches_for_nothing(client) -> None:
    """A family saying "thank you" must not produce a plan."""
    runner = client.app.state.container.runner
    patient = client.app.state.container.world.patients()[0]
    nothing_asked = PatientRequest(
        id="r-test-2",
        patient_id=patient.id,
        raw_text="dhonnobad",
        intent=RequestIntent.UNCLEAR,
    )

    assert await runner.replan_for_request(patient.id, nothing_asked) is None


async def test_an_unknown_family_is_not_an_error(client) -> None:
    runner = client.app.state.container.runner
    assert await runner.replan_for_request("NOBODY", _reading("NOBODY")) is None


def _with_tolerance(hospital_id: str, kind, days: int):
    """The hospital's saved rules, with a stated tolerance for one step.

    Built rather than skipped around: a hospital that has said how far a step
    may move is the whole precondition for this search, so a test that skips
    when none is configured is a test that never runs.
    """
    policy = default_policy(hospital_id)
    step = policy.steps.get(kind.value)
    updated = (
        step.model_copy(update={"shift_tolerance_days": days})
        if step is not None
        else StepPolicy(kind=kind, shift_tolerance_days=days)
    )
    return policy.model_copy(update={"steps": {**policy.steps, kind.value: updated}})


async def test_the_search_is_recorded_where_the_console_reads_it(client) -> None:
    """The search has to land in `runner.searches`, because that is the only
    place `/patients/{id}/search` looks."""
    container = client.app.state.container
    runner = container.runner
    patient = container.world.patients()[0]
    target = container.world.target_kind_for(patient.id)
    runner.planner.rules_for = lambda _h: _with_tolerance(patient.hospital_id, target, 7)

    search = await runner.replan_for_request(patient.id, _reading(patient.id))

    assert search is not None
    assert runner.searches[patient.id] is search
    assert search.step_kind == target.value
    assert search.summary(), "a search with no summary tells a reader nothing"

    served = client.get(f"/api/patients/{patient.id}/search").json()
    assert served["summary"] == search.summary(), (
        "the API must serve the same search the runner recorded"
    )


class TestTheConfirmEndpoint:
    def test_confirming_returns_the_search_it_ran(self, client) -> None:
        """So the Console can show the working without a second round trip —
        and so a missing search is visible rather than silently absent."""
        runner = client.app.state.container.runner
        patient = client.app.state.container.world.patients()[0]
        runner.requests.setdefault(patient.id, []).append(_reading(patient.id).model_copy(
            update={"confirmed_by": None}
        ))

        response = client.post(
            f"/api/patients/{patient.id}/requests/r-test-1/confirm"
        )

        assert response.status_code == 200
        assert "search" in response.json(), (
            "the endpoint must say what it searched, even when that is null"
        )

    def test_an_unknown_request_is_a_404_not_a_search(self, client) -> None:
        patient = client.app.state.container.world.patients()[0]
        response = client.post(f"/api/patients/{patient.id}/requests/nope/confirm")
        assert response.status_code == 404


# --------------------------------------------------- the turn that offers back


@pytest.mark.anyio
async def test_a_search_that_finds_a_day_puts_it_to_the_family(client) -> None:
    """A system that only ever asks leaves the family doing the planning.

    `ask_family` poses a question and waits. This is the other half: the day
    the planner found goes back to them, with what it would likely cost, and
    asks whether it suits — so the next reply is either agreement or the
    constraint that makes a better plan.
    """
    container = client.app.state.container
    runner = container.runner
    patient = container.world.patients()[0]
    target = container.world.target_kind_for(patient.id)
    runner.planner.rules_for = lambda _h: _with_tolerance(patient.hospital_id, target, 7)

    search = await runner.replan_for_request(patient.id, _reading(patient.id))
    assert search is not None

    asked = runner.conversation.pending(patient.id)
    assert asked is not None, "the planner found a day and told nobody"
    assert asked.reason.value == "plan_proposed"
    assert asked.asked_text, "a proposal with no text is not a proposal"

    # The day in the message is the day it found, and the guard has already
    # refused any text naming a date it was not handed.
    offered = runner.options[patient.id].options[0]
    assert asked.about_day == offered.target_on.isoformat()


@pytest.mark.anyio
async def test_a_family_who_told_us_a_figure_is_shown_their_own(client) -> None:
    """Their number is evidence; ours is arithmetic. Never correct them."""
    container = client.app.state.container
    runner = container.runner
    patient = container.world.patients()[0]

    costed = runner.cost_of_visit(patient.id, people=2)
    assert costed is None or not costed.any_stated

    base = _reading(patient.id)
    reading = base.model_copy(update={
        "travel": base.travel.model_copy(update={
            "stated_cost_inr": 900,
            "stated_in": "Trainer tickets 900 taka hobe",
        })
    })
    runner.requests.setdefault(patient.id, []).append(reading)

    theirs = runner.cost_of_visit(patient.id, people=2)
    assert theirs is not None and theirs.any_stated
    travel = next(i for i in theirs.items if i.stated)
    assert travel.low_paise == travel.high_paise == 90_000
    assert "900 taka" in travel.said
