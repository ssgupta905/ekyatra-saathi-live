"""Getting back to "nobody has been asked yet" without deleting anything.

`reset` rewinds the world and refuses outright on real records, which is
right: it would delete patients, steps and plans somebody entered. But a
rehearsal needs a clean start, and the things in the way are not records —
they are working state the process happens to be holding.

This cost three takes of a film to find. The demo called `reset`, `reset`
raised on a real world, the caller had swallowed the error, and three copies
of the same family's request accumulated on screen across three runs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from saathi.domain.requests import PatientRequest, RequestIntent
from saathi.language.questions import AskReason, AskTopic
from saathi.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _busy(runner, patient_id: str) -> None:
    """Put the runner into the state a finished take leaves behind."""
    runner.conversation.open_question(
        patient_id=patient_id, reason=AskReason.DOCTOR_AWAY,
        topics=(AskTopic.TIMING,), asked_text="(asked)",
        language=runner.world.patient(patient_id).language, about_day="2026-11-27",
    )
    runner.requests.setdefault(patient_id, []).append(
        PatientRequest(id="req-1", patient_id=patient_id, raw_text="…",
                       intent=RequestIntent.MOVE_VISIT)
    )


async def test_clearing_forgets_what_was_asked_and_read(client) -> None:
    runner = client.app.state.container.runner
    patient_id = client.app.state.container.world.patients()[0].id
    _busy(runner, patient_id)

    await runner.forget_working_state()

    assert runner.conversation.waiting() == ()
    assert runner.requests == {}
    assert runner.searches == {}


async def test_clearing_deletes_no_record(client) -> None:
    """The whole reason this exists instead of `reset`."""
    container = client.app.state.container
    runner = container.runner
    before_patients = [p.id for p in container.world.patients()]
    before_steps = {p: len(container.world.steps_for(p)) for p in before_patients}
    _busy(runner, before_patients[0])

    await runner.forget_working_state()

    assert [p.id for p in container.world.patients()] == before_patients
    assert {p: len(container.world.steps_for(p)) for p in before_patients} == before_steps


async def test_a_connector_forgets_what_it_acted_on(client) -> None:
    """A connector acts once per leave. Without this, a second rehearsal of
    the same scenario shows nothing at all."""
    from saathi.live.hospital_sync import HospitalSync

    runner = client.app.state.container.runner
    sync = HospitalSync(hospital=None, runner=runner, hospital_id="H1")
    sync._seen_leave.add("leave-1")
    sync._acted_on_orders.add("order-1")
    runner.hospital_syncs["H1"] = sync

    await runner.forget_working_state()

    assert sync._seen_leave == set()
    assert sync._acted_on_orders == set()
    assert not sync.snapshot.primed, "the snapshot must re-prime, not re-report everything"


class TestTheApiGuard:
    def test_clear_is_allowed_even_on_real_records(self, client) -> None:
        client.app.state.container.world.real = True
        try:
            response = client.post("/api/live/control", json={"action": "clear"})
        finally:
            client.app.state.container.world.real = False
        assert response.status_code == 200

    def test_reset_is_still_refused_on_real_records(self, client) -> None:
        """It would delete patients somebody entered. That guard stays."""
        client.app.state.container.world.real = True
        try:
            response = client.post("/api/live/control", json={"action": "reset"})
        finally:
            client.app.state.container.world.real = False
        assert response.status_code == 409
        assert "clear" in response.json()["detail"], (
            "the refusal should name the thing the caller should use instead"
        )

    def test_the_clock_is_still_refused_on_real_records(self, client) -> None:
        client.app.state.container.world.real = True
        try:
            refused = [
                client.post("/api/live/control", json={"action": action}).status_code
                for action in ("play", "pause", "step")
            ]
        finally:
            client.app.state.container.world.real = False
        assert refused == [409, 409, 409]
