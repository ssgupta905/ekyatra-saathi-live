"""Regression tests for races that only appear under real load.

Planning runs on worker threads while the event loop also writes. Each test
here failed against the code that existed before the fixes.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from datetime import date

import httpx
import pytest
from saathi.bootstrap.container import build_container
from saathi.config import Settings
from saathi.domain.enums import SourceSystem
from saathi.ledger.evidence import InMemoryEvidenceLedger
from saathi.live.events import EventBus
from saathi.main import create_app


@pytest.fixture
def fast_switching():
    """Make the interpreter swap threads far more often, so races show up."""
    original = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    yield
    sys.setswitchinterval(original)


def test_concurrent_appends_never_fork_the_hash_chain(fast_switching):
    ledger = InMemoryEvidenceLedger()
    threads, per_thread = 8, 150

    def writer(n: int) -> None:
        for i in range(per_thread):
            ledger.record(
                f"P{n}", SourceSystem.DERIVED, f"rec-{n}-{i}", f"claim {i}", {"n": n}
            )

    workers = [threading.Thread(target=writer, args=(n,)) for n in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()

    entries = ledger.all_entries()
    assert len(entries) == threads * per_thread
    assert ledger.verify(), "the chain no longer verifies: two writers chained to one head"
    heads = [e.previous_hash for e in entries]
    assert len(set(heads)) == len(heads), "two entries share a previous_hash: the chain forked"


def test_record_once_from_many_threads_records_a_fact_once(fast_switching):
    ledger = InMemoryEvidenceLedger()

    def writer() -> None:
        for _ in range(100):
            ledger.record_once("P1", SourceSystem.DERIVED, "same", "the same claim")

    workers = [threading.Thread(target=writer) for _ in range(8)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()

    assert ledger.size() == 1
    assert ledger.verify()


async def test_publishing_from_a_worker_thread_reaches_subscribers():
    bus = EventBus()
    bus.bind_loop(asyncio.get_running_loop())
    loop_thread = threading.get_ident()

    # asyncio.Queue is not thread-safe, so every delivery must happen on the
    # loop's own thread no matter which thread published.
    delivered_on: set[int] = set()
    deliver = bus._deliver

    def recording_deliver(event):
        delivered_on.add(threading.get_ident())
        deliver(event)

    bus._deliver = recording_deliver

    async with bus.subscribe() as queue:
        done = threading.Event()

        def publisher() -> None:
            for i in range(50):
                bus.publish("clock.tick", "2026-09-25", summary=f"event {i}")
            done.set()

        thread = threading.Thread(target=publisher)
        thread.start()
        received = [await asyncio.wait_for(queue.get(), timeout=2) for _ in range(50)]
        thread.join()

    assert done.is_set()
    assert delivered_on == {loop_thread}, "events were put on a queue from a non-loop thread"
    assert [e.seq for e in received] == sorted(e.seq for e in received)
    assert len({e.seq for e in received}) == 50, "sequence numbers collided across threads"


async def test_recompute_does_not_block_the_event_loop():
    """`/plan?recompute=true` can call a language model; it must not stall the loop."""
    app = create_app()
    state = build_container(Settings(_env_file=None), today=date(2026, 9, 25))
    app.state.container = state
    original = state.planner.plan_visit

    def slow(*args, **kwargs):
        time.sleep(0.4)
        return original(*args, **kwargs)

    state.planner.plan_visit = slow

    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            patient_id = state.cohort.patients[0].id
            response = await client.post(
                "/api/plan?recompute=true", json={"patient_id": patient_id}
            )
    finally:
        task.cancel()

    assert response.status_code == 200
    assert ticks >= 15, f"the loop only advanced {ticks} times during a 0.4s planner call"
