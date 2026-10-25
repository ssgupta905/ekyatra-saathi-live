"""The event stream.

Everything the live world does emits one of these, and every event carries the
*measured* wall-clock duration of the work it describes. That number is the
demo's whole claim: a judge watching "planner re-ran P0003 · 41 ms" is watching
a real run, not a replayed recording. So `duration_ms` is always timed, never
estimated, and an event with no work behind it carries none.

The bus is a plain fan-out over `asyncio.Queue`. A slow subscriber drops events
rather than stalling the world — a console that cannot keep up should fall
behind visibly, not hold up the simulation.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

#: One subscriber's backlog. Past this, its oldest events are dropped.
QUEUE_LIMIT = 500


class EventKind:
    """The closed vocabulary of things that can happen."""

    CLOCK_TICK = "clock.tick"
    DESK_CANDIDATE = "desk.candidate"
    DESK_CONFIRMED = "desk.confirmed"
    STEP_RELEASED = "step.released"
    PLAN_RECOMPUTED = "plan.recomputed"
    MESSAGE_RENDERED = "message.rendered"
    MESSAGE_HELD = "message.held"
    INBOUND_RECEIVED = "inbound.received"
    GUARD_BLOCKED = "guard.blocked"
    LEDGER_APPENDED = "ledger.appended"
    ALERT_RAISED = "alert.raised"
    METRICS_UPDATED = "metrics.updated"
    WORLD_RESET = "world.reset"
    RUNNER_STATE = "runner.state"
    #: A desk's one-tap report that a resource is unavailable.
    DISRUPTION_RAISED = "disruption.raised"
    #: Sent to an affected family before any new date is computed.
    HOLDING_MESSAGE_SENT = "holding_message.sent"
    #: Ranked options are ready for a navigator/doctor to choose from.
    OPTIONS_READY = "options.ready"
    #: A navigator/doctor picked an option; the approval itself was logged.
    APPROVAL_RECORDED = "approval.recorded"
    #: A family confirmed a message — IVR press-1 or a WhatsApp reply.
    CONFIRMATION_RECEIVED = "confirmation.received"
    #: A process-only answer was sent in reply to an inbound question.
    PROCESS_ANSWERED = "process.answered"
    #: Work has begun and has not finished. Published *before* the work, so a
    #: console can show that something is happening rather than leaving a user
    #: watching an unchanged screen and guessing.
    AGENT_STARTED = "agent.started"
    #: The same work, finished, carrying what it actually cost.
    AGENT_FINISHED = "agent.finished"
    #: The family chose the language they are written to in. A preference on
    #: their record, not a view setting, so it belongs in the event log.
    LANGUAGE_CHANGED = "language.changed"
    #: A fact source was consulted — see `tools/`. Carries the claim, the
    #: provider and the measured latency, so a number on screen can be traced
    #: back to the call that produced it.
    TOOL_CALLED = "tool.called"


@dataclass(frozen=True)
class WorldEvent:
    kind: str
    #: Real time, for ordering and for the console's "3s ago".
    at: datetime
    #: Simulated date the work happened on.
    sim_date: str
    patient_id: str | None = None
    #: Short sentence a navigator can read without expanding anything.
    summary: str = ""
    #: Measured duration of the work, when there was work to measure.
    duration_ms: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    seq: int = 0

    def to_json(self) -> dict:
        return {
            "kind": self.kind,
            "at": self.at.isoformat(),
            "sim_date": self.sim_date,
            "patient_id": self.patient_id,
            "summary": self.summary,
            "duration_ms": self.duration_ms,
            "payload": self.payload,
            "seq": self.seq,
        }


class EventBus:
    """Fan-out to every open console, plus a short replay buffer.

    `publish` is safe from any thread. Planning and tool lookups run on worker
    threads, and `asyncio.Queue` is not thread-safe: delivering to it from off
    the event loop can drop a wake-up and leave a console waiting on an event
    that is already queued. So once the bus is bound to its loop, an off-loop
    publish hands delivery to that loop; ordering and history are fixed first,
    under a lock, so sequence numbers stay strictly increasing either way.
    """

    def __init__(self, history: int = 200) -> None:
        self._subscribers: set[asyncio.Queue[WorldEvent]] = set()
        self._history: deque[WorldEvent] = deque(maxlen=history)
        self._seq = 0
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Name the loop that owns the subscriber queues. Called once at startup."""
        self._loop = loop

    def publish(
        self,
        kind: str,
        sim_date: str,
        *,
        patient_id: str | None = None,
        summary: str = "",
        duration_ms: float | None = None,
        **payload: Any,
    ) -> WorldEvent:
        with self._lock:
            self._seq += 1
            event = WorldEvent(
                kind=kind,
                at=datetime.now(UTC),
                sim_date=sim_date,
                patient_id=patient_id,
                summary=summary,
                duration_ms=duration_ms,
                payload=payload,
                seq=self._seq,
            )
            self._history.append(event)
        self._dispatch(event)
        return event

    def _dispatch(self, event: WorldEvent) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed() and not self._on_loop(loop):
            loop.call_soon_threadsafe(self._deliver, event)
        else:
            self._deliver(event)

    @staticmethod
    def _on_loop(loop: asyncio.AbstractEventLoop) -> bool:
        try:
            return asyncio.get_running_loop() is loop
        except RuntimeError:
            return False

    def _deliver(self, event: WorldEvent) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop this subscriber's oldest and take the newest: a console
                # that fell behind wants the present, not the backlog.
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(event)

    def recent(self, limit: int = 50) -> list[WorldEvent]:
        with self._lock:
            return list(self._history)[-limit:]

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[WorldEvent]]:
        queue: asyncio.Queue[WorldEvent] = asyncio.Queue(maxsize=QUEUE_LIMIT)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
