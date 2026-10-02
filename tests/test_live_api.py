"""The live HTTP surface, with no credentials and no network.

This is the configuration CI runs and the one a judge gets if the wifi dies:
no Groq key, so no actors and no language layer. Everything that makes the
demo *true* rather than merely pretty — the clock, the real re-planning, the
real guard, the ledger — has to work here.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from saathi.api.deps import build_state
from saathi.api.live import QUEUE_LIMIT, stream
from saathi.config import Settings
from saathi.live.events import EventBus
from saathi.main import create_app
from starlette.requests import Request


def _request(app) -> Request:
    """The thinnest thing the stream endpoint needs: an app to read state off."""
    return Request({"type": "http", "method": "GET", "path": "/api/stream",
                    "headers": [], "app": app})


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def test_health_reports_the_world_not_just_the_process(client):
    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["ledger_intact"] is True
    assert body["running"] is False, "the clock must not start without being asked"
    assert body["language_layer"] is False
    assert body["actors"] is False
    assert body["sim_date"]


def test_the_console_opens_on_real_decisions_not_an_empty_page(client):
    """The runner plans once at startup, before anyone connects."""
    snapshot = client.get("/api/live").json()

    assert snapshot["counters"]["plan_runs"] == snapshot["patients"]
    assert snapshot["metrics"]["patients"] == snapshot["patients"]
    assert len(snapshot["watched"]) <= snapshot["patients"]


def test_stepping_advances_exactly_one_day(client):
    before = client.get("/api/live").json()
    after = client.post("/api/live/control", json={"action": "step"}).json()

    assert after["day"] == before["day"] + 1
    assert after["current"] > before["current"]


def test_play_and_pause_are_reflected(client):
    assert client.post("/api/live/control", json={"action": "play"}).json()["running"] is True
    assert client.post("/api/live/control", json={"action": "pause"}).json()["running"] is False


def test_speed_needs_a_value(client):
    assert client.post("/api/live/control", json={"action": "speed"}).status_code == 422
    body = client.post(
        "/api/live/control", json={"action": "speed", "seconds_per_day": 2.0}
    ).json()
    assert body["seconds_per_day"] == 2.0


def test_an_unknown_action_is_refused(client):
    assert client.post("/api/live/control", json={"action": "fast-forward"}).status_code == 422


def test_reading_a_plan_does_not_grow_the_ledger(client):
    """In a live world the console reflects the world; it must not cause it."""
    patient_id = client.get("/api/patients").json()[0]["id"]
    before = client.get("/api/health").json()["ledger_entries"]

    for _ in range(3):
        body = client.post("/api/plan", json={"patient_id": patient_id}).json()

    assert body["plan"] is not None
    assert body["sim_date"], "a cached run should say when it was decided"
    assert body["plan_ms"] is not None
    assert client.get("/api/health").json()["ledger_entries"] == before


def test_a_plan_can_still_be_forced_for_a_scripted_run(client):
    patient_id = client.get("/api/patients").json()[0]["id"]
    body = client.post(
        "/api/plan", params={"recompute": "true"}, json={"patient_id": patient_id}
    ).json()

    assert body["plan"]["patient_id"] == patient_id
    assert body["sim_date"] is None, "a fresh run is not a cached one"


async def test_the_stream_replays_what_already_happened():
    """A console connecting mid-demo opens with context, not a blank log.

    The generator is pulled directly rather than through a client: the stream
    is endless by design, and every ASGI test transport waits for the response
    to finish before it will let go of one.
    """
    app = create_app()
    state = build_state(Settings(_env_file=None), today=date(2026, 9, 25))
    app.state.saathi = state
    await state.runner.plan_all()
    await state.runner.tick()

    response = await stream(_request(app))
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache, no-transform"
    # Without this a proxy buffers the whole stream, which is the opposite of live.
    assert response.headers["x-accel-buffering"] == "no"

    frames = []
    body = response.body_iterator
    try:
        for _ in range(6):
            frames.append(await anext(body))
    finally:
        await body.aclose()

    kinds = [f.split("\n")[0].removeprefix("event: ") for f in frames]
    payloads = [json.loads(f.split("data: ", 1)[1]) for f in frames]

    assert "clock.tick" in kinds
    assert all("sim_date" in p and "summary" in p for p in payloads)
    timed = [p for p in payloads if p["duration_ms"] is not None]
    assert timed, "nothing on the stream carried a measured duration"
    assert all(p["duration_ms"] > 0 for p in timed)


async def test_the_stream_closing_releases_its_subscription():
    """A console that goes away must not leave the bus fanning out to nobody."""
    app = create_app()
    app.state.saathi = build_state(Settings(_env_file=None), today=date(2026, 9, 25))
    bus = app.state.saathi.bus

    response = await stream(_request(app))
    body = response.body_iterator
    await anext(body)
    assert bus.subscriber_count == 1

    await body.aclose()
    assert bus.subscriber_count == 0


async def test_every_open_console_sees_the_same_event():
    """Two navigators watching the same world must not see different worlds."""
    bus = EventBus()
    async with bus.subscribe() as first, bus.subscribe() as second:
        bus.publish("clock.tick", "2026-09-25", summary="Day 1")
        assert (await first.get()).summary == "Day 1"
        assert (await second.get()).summary == "Day 1"
    assert bus.subscriber_count == 0


async def test_a_console_that_falls_behind_drops_history_not_the_world():
    """Back-pressure must never stall the simulation for everyone else."""
    bus = EventBus()
    async with bus.subscribe() as queue:
        for i in range(QUEUE_LIMIT + 25):
            bus.publish("clock.tick", "2026-09-25", summary=f"Day {i}")

        assert queue.qsize() == QUEUE_LIMIT
        seen = {queue.get_nowait().summary for _ in range(QUEUE_LIMIT)}
        assert f"Day {QUEUE_LIMIT + 24}" in seen, "the newest event was dropped"
        assert "Day 0" not in seen, "the oldest event was kept instead"


def test_the_desk_gates_every_release(client):
    """Nothing becomes available without something confirming it."""
    for _ in range(4):
        client.post("/api/live/control", json={"action": "step"})

    queue = client.get("/api/desk/queue").json()
    if not queue:
        pytest.skip("no release came due in four days for this seed")

    candidate = queue[0]
    step_id = candidate["step_id"]
    patient_id = candidate["patient_id"]

    steps = {s["id"]: s for s in client.get(f"/api/patients/{patient_id}/steps").json()}
    assert steps[step_id]["status"] == "pending_result"

    assert client.post("/api/desk/confirm", json={"candidate_id": candidate["id"]}).json() == {
        "confirmed": True
    }

    steps = {s["id"]: s for s in client.get(f"/api/patients/{patient_id}/steps").json()}
    assert steps[step_id]["status"] == "result_available"


def test_confirming_the_same_candidate_twice_is_refused(client):
    for _ in range(4):
        client.post("/api/live/control", json={"action": "step"})
    queue = client.get("/api/desk/queue").json()
    if not queue:
        pytest.skip("no release came due in four days for this seed")

    candidate_id = queue[0]["id"]
    client.post("/api/desk/confirm", json={"candidate_id": candidate_id})
    assert (
        client.post("/api/desk/confirm", json={"candidate_id": candidate_id}).status_code == 404
    )


def test_an_injected_clinical_question_is_held_by_the_real_guard(client):
    patient_id = client.get("/api/patients").json()[0]["id"]
    body = client.post(
        "/api/live/inject",
        json={"patient_id": patient_id, "text": "report mein kya aaya? cancer hai kya?"},
    ).json()

    assert body["answerable"] is False
    assert body["triggers"]
    assert body["origin"] == "typed"

    alerts = client.get("/api/alerts").json()
    assert any(a["patient_id"] == patient_id for a in alerts)


def test_an_injected_logistics_question_is_answerable(client):
    patient_id = client.get("/api/patients").json()[0]["id"]
    body = client.post(
        "/api/live/inject",
        json={"patient_id": patient_id, "text": "train ka kiraya kitna lagega?"},
    ).json()

    assert body["answerable"] is True
    assert client.get("/api/alerts").json() == []


def test_injection_without_actors_and_without_text_is_refused(client):
    """Nothing invents a family's words when there is nothing to write them."""
    patient_id = client.get("/api/patients").json()[0]["id"]
    assert client.post("/api/live/inject", json={"patient_id": patient_id}).status_code == 503


def test_the_actor_surfaces_say_so_when_there_is_no_key(client):
    """Off is a state the console can show, not an error it has to handle."""
    patient_id = client.get("/api/patients").json()[0]["id"]

    brief = client.get(f"/api/patients/{patient_id}/brief").json()
    assert brief == {"available": False, "lines": [], "reason": "GROQ_API_KEY not set"}

    narration = client.post(
        f"/api/patients/{patient_id}/narration",
        json={"nodes": [{"id": "gate", "text": "One prerequisite is still outstanding."}]},
    ).json()
    assert narration["available"] is False
    assert narration["nodes"] == []


def test_the_ledger_stays_verifiable_across_a_week_of_simulated_days(client):
    for _ in range(7):
        client.post("/api/live/control", json={"action": "step"})

    health = client.get("/api/health").json()
    assert health["ledger_intact"] is True
    # One row per fact that actually changed, not one per planning run.
    assert health["ledger_entries"] < health["patients"] * 10
