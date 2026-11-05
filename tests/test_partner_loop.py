"""The background loop that lets the network answer without anyone asking it to.

Every other partner test calls `settle_partners` by hand, which proves the
answer is right but never that anything would call it. That gap is invisible in
a test suite and loud in a demonstration: the chain simply stops, with no error
anywhere, because the task that drives it was never started.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from saathi.config import get_settings
from saathi.domain.enums import ReadinessStatus, Role
from saathi.main import create_app

PASSWORD = "correct horse battery"


@pytest.fixture
def net(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/loop.db")
    monkeypatch.setenv("SAATHI_SEED_DEMO", "true")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        container = client.app.state.container
        container.identity.add_user("neha", "Neha", Role.ADMIN, PASSWORD)
        token = client.post(
            "/api/auth/login", json={"username": "neha", "password": PASSWORD}
        ).json()["token"]
        client.headers["authorization"] = f"Bearer {token}"
        client.container = container
        yield client
    get_settings.cache_clear()


def test_the_partner_loop_is_running_once_the_app_has_started(net):
    """The task exists and is not already finished.

    Nothing else checks this. `settle_partners` is correct and well tested; it
    just never ran in a real process, because the task that calls it every five
    seconds was not alive.
    """
    runner = net.container.runner

    assert runner.partners is not None, "the real world should have a partner desk"
    task = getattr(runner, "_partner_task", None)
    assert task is not None, "nothing settles the network's answers"
    assert not task.done(), f"the partner loop stopped: {task!r}"


def test_a_due_answer_settles_without_anyone_calling_settle(net):
    """Wind the desk's clock forward and let the loop do the work.

    The loop wakes every five seconds, so this waits for it rather than calling
    the method — which is the whole point of the test.
    """
    runner = net.container.runner
    world = net.container.world

    pending = [
        (p.id, item)
        for p in world.patients()
        for item in world.readiness_for(p.id)
        if item.status is ReadinessStatus.PENDING and item.partner_id
    ]
    assert pending, "no family is waiting on the network; nothing to settle"

    # Every simulated organisation is overdue from here on.
    runner.partners._now = lambda: datetime.now(UTC) + timedelta(hours=1)

    async def wait_for_an_answer() -> bool:
        for _ in range(80):  # up to 8s: the loop's period is 5s
            for patient_id, item in pending:
                now = next(
                    (i for i in world.readiness_for(patient_id) if i.id == item.id), None
                )
                if now is not None and now.status is not ReadinessStatus.PENDING:
                    return True
            await asyncio.sleep(0.1)
        return False

    assert net.portal.call(wait_for_an_answer), (
        "nothing answered in eight seconds; the loop is not settling due requests"
    )


def test_the_loop_still_settles_for_families_loaded_after_startup(net):
    """The demo's own path: load the cast through the API, then wait.

    Every other test works on families the container seeded at boot. The
    demonstration does not: an administrator types three addresses and the cast
    arrives minutes later. If anything about that path leaves the new families
    outside what the loop watches, the chain stops for exactly the families
    being shown — and for nobody else, which is the worst way to find out.
    """
    runner = net.container.runner
    world = net.container.world

    loaded = net.post(
        "/api/demo/cast",
        json={"emails": ["one@example.test", "two@example.test", "three@example.test"]},
    )
    assert loaded.status_code == 200, loaded.text
    ids = [f["patient_id"] for f in loaded.json()["families"]]

    pending = [
        (pid, item)
        for pid in ids
        for item in world.readiness_for(pid)
        if item.status is ReadinessStatus.PENDING and item.partner_id
    ]
    assert pending, f"no demo family was asked anything: {ids}"

    runner.partners._now = lambda: datetime.now(UTC) + timedelta(hours=1)

    async def wait_for_an_answer() -> bool:
        for _ in range(100):  # up to 10s against a 5s loop
            for patient_id, item in pending:
                now = next((i for i in world.readiness_for(patient_id) if i.id == item.id), None)
                if now is not None and now.status is not ReadinessStatus.PENDING:
                    return True
            await asyncio.sleep(0.1)
        return False

    assert net.portal.call(wait_for_an_answer), (
        "the demo's own families were never answered; the chain stops mid-demonstration"
    )
