"""A family's ask, from the question to a navigator agreeing with it.

The pieces this exercises were all built before and none of them was
reachable: `main.py` registered seventeen routers and not one for a patient
request, so a reading went into memory and stopped there. These tests pin the
loop end to end over HTTP, and in particular the two properties that make it
safe to run a language model in it at all:

* the planner never sees a request a person has not agreed to, and
* a figure with no sentence behind it never reaches a navigator's screen.

No Groq key here, which is the configuration CI runs and the one a judge gets
if the wifi dies. So the reading is injected the way the extractor would have
produced it, and everything after that is the real path.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from saathi.domain.enums import Language
from saathi.domain.requests import PatientRequest, RequestConstraint, RequestIntent, TravelFacts
from saathi.language.questions import AskReason, AskTopic
from saathi.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _runner(client: TestClient):
    return client.app.state.container.runner


def _patient_id(client: TestClient) -> str:
    return client.app.state.container.world.patients()[0].id


def _reading(
    client: TestClient,
    *,
    request_id: str = "req-1",
    travel: TravelFacts | None = None,
    intent: RequestIntent = RequestIntent.MOVE_VISIT,
) -> PatientRequest:
    """Put a reading in the queue the way `_raise_request` would have."""
    runner = _runner(client)
    patient_id = _patient_id(client)
    request = PatientRequest(
        id=request_id,
        patient_id=patient_id,
        raw_text="Amar sathe ami jabo. Trainer tickets 900 taka hobe. 1 tarikher age noy.",
        gloss="I will go with her. Train tickets will be 900. Not before the 1st.",
        intent=intent,
        constraint=RequestConstraint(not_before=date(2026, 12, 1), reason="salary on the 1st"),
        travel=travel or TravelFacts(),
        confidence="high",
    )
    runner.requests.setdefault(patient_id, []).append(request)
    return request


class TestTheQueue:
    def test_a_reading_waits_for_a_person(self, client: TestClient) -> None:
        _reading(client)

        (row,) = client.get("/api/requests/waiting").json()

        assert row["id"] == "req-1"
        assert row["intent"] == "move_visit"
        assert row["constraint"]["not_before"] == "2026-12-01"
        assert row["gloss"], "a navigator who does not read Bengali still has to decide"

    def test_the_queue_is_empty_before_anybody_asks(self, client: TestClient) -> None:
        assert client.get("/api/requests/waiting").json() == []

    def test_a_decided_request_leaves_the_queue(self, client: TestClient) -> None:
        request = _reading(client)
        patient_id = request.patient_id

        client.post(f"/api/patients/{patient_id}/requests/req-1/confirm")

        assert client.get("/api/requests/waiting").json() == []

    def test_what_needs_a_person_sorts_first(self, client: TestClient) -> None:
        """A request the planner can act on will be, the moment it is agreed.

        One that needs money, papers or transport needs a human either way,
        and leaving those at the bottom of a queue is how they go cold.
        """
        _reading(client, request_id="req-plannable", intent=RequestIntent.MOVE_VISIT)
        _reading(client, request_id="req-human", intent=RequestIntent.NEEDS_HELP)

        rows = client.get("/api/requests/waiting").json()

        assert [row["id"] for row in rows] == ["req-human", "req-plannable"]


class TestAttribution:
    def test_a_stated_figure_reaches_the_navigator_with_its_sentence(
        self, client: TestClient
    ) -> None:
        _reading(
            client,
            travel=TravelFacts(
                companions=1,
                stated_cost_inr=900,
                stated_in="Trainer tickets 900 taka hobe",
            ),
        )

        (row,) = client.get("/api/requests/waiting").json()

        assert row["travel"]["stated_cost_inr"] == 900
        assert row["travel"]["stated_in"] == "Trainer tickets 900 taka hobe"
        assert row["travel"]["companions"] == 1

    def test_a_figure_with_no_sentence_behind_it_is_not_shown(
        self, client: TestClient
    ) -> None:
        """This is the whole reason the project refused to hold money at all.

        A rupee figure with nothing attributing it to the family is
        indistinguishable from one this system invented, and the Console must
        not be the place that blurs the two. Dropping it is the right outcome:
        a navigator who cannot see a figure asks, and a navigator shown an
        invented one acts on it.
        """
        _reading(client, travel=TravelFacts(stated_cost_inr=900))  # no `stated_in`

        (row,) = client.get("/api/requests/waiting").json()

        assert "travel" not in row

    def test_no_travel_block_when_the_family_said_nothing(self, client: TestClient) -> None:
        _reading(client)
        (row,) = client.get("/api/requests/waiting").json()
        assert "travel" not in row


class TestConfirming:
    def test_confirming_records_who_and_replans(self, client: TestClient) -> None:
        request = _reading(client)
        patient_id = request.patient_id

        body = client.post(f"/api/patients/{patient_id}/requests/req-1/confirm").json()

        assert body["request"]["confirmed_by"]
        assert body["request"]["confirmed_at"]
        assert "decision" in body

    def test_an_unconfirmed_request_is_not_actionable(self, client: TestClient) -> None:
        """The invariant the two-step exists for."""
        request = _reading(client)
        assert not request.actionable

    def test_a_confirmed_move_request_becomes_actionable(self, client: TestClient) -> None:
        request = _reading(client)
        patient_id = request.patient_id
        client.post(f"/api/patients/{patient_id}/requests/req-1/confirm")

        confirmed = _runner(client).requests[patient_id][0]
        assert confirmed.actionable

    def test_confirming_twice_is_a_404_not_an_overwrite(self, client: TestClient) -> None:
        """Who decided, and when, must not be quietly replaced by a double tap."""
        request = _reading(client)
        patient_id = request.patient_id

        first = client.post(f"/api/patients/{patient_id}/requests/req-1/confirm")
        second = client.post(f"/api/patients/{patient_id}/requests/req-1/confirm")

        assert first.status_code == 200
        assert second.status_code == 404

    def test_an_unknown_request_is_a_404(self, client: TestClient) -> None:
        patient_id = _patient_id(client)
        assert (
            client.post(f"/api/patients/{patient_id}/requests/nope/confirm").status_code
            == 404
        )


class TestRejecting:
    def test_rejecting_keeps_the_reading_and_the_correction(
        self, client: TestClient
    ) -> None:
        """A rejected reading is the most useful thing in this loop.

        It is the only evidence that the extractor got something wrong.
        Deleting it would leave no way to tell a model that mishears dates
        from one that was never run.
        """
        request = _reading(client)
        patient_id = request.patient_id

        body = client.post(
            f"/api/patients/{patient_id}/requests/req-1/reject",
            json={"reason": "she said after the 20th, not on the 20th"},
        ).json()

        assert body["request"]["rejected_reason"].startswith("she said after")
        assert body["request"]["raw_text"], "the family's own words are kept"
        stored = _runner(client).requests[patient_id][0]
        assert not stored.actionable

    def test_a_rejection_needs_a_reason(self, client: TestClient) -> None:
        request = _reading(client)
        patient_id = request.patient_id

        response = client.post(
            f"/api/patients/{patient_id}/requests/req-1/reject", json={"reason": ""}
        )

        assert response.status_code == 422

    def test_a_rejected_request_cannot_then_be_confirmed(self, client: TestClient) -> None:
        request = _reading(client)
        patient_id = request.patient_id
        client.post(
            f"/api/patients/{patient_id}/requests/req-1/reject",
            json={"reason": "misread"},
        )

        assert (
            client.post(f"/api/patients/{patient_id}/requests/req-1/confirm").status_code
            == 404
        )


class TestOpenQuestions:
    def test_a_question_nobody_answered_is_visible(self, client: TestClient) -> None:
        """Otherwise a family who never replied is visible nowhere at all.

        They are the ones most likely to turn up on the wrong day, or not at
        all, and a queue that only shows answers hides exactly them.
        """
        patient_id = _patient_id(client)
        _runner(client).conversation.open_question(
            patient_id=patient_id,
            reason=AskReason.DOCTOR_AWAY,
            topics=(AskTopic.TIMING, AskTopic.COST),
            asked_text="27 নভেম্বর তারিখে ডাক্তার উপস্থিত থাকবেন না।",
            language=Language.BENGALI,
            about_day="2026-11-27",
        )

        (row,) = client.get("/api/questions/waiting").json()

        assert row["patient_id"] == patient_id
        assert row["reason"] == "doctor_away"
        assert set(row["topics"]) == {"timing", "cost"}
        assert row["language"] == "bn"
        assert "waiting" in row["summary"]

    def test_no_open_questions_before_anything_is_asked(self, client: TestClient) -> None:
        assert client.get("/api/questions/waiting").json() == []
