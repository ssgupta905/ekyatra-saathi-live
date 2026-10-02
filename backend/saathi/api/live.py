"""The live surface: the clock, the stream, and the things an operator can do.

The console reads the world through here and, with two exceptions, cannot
change it. The exceptions are deliberate and both are *inputs*, not decisions: a
desk clerk confirming a record, and a person putting a message in a family's
mouth. Everything that follows from either — re-planning, rendering, guarding,
scoring — happens because the system reacted, not because the endpoint said so.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..live.events import QUEUE_LIMIT as _QUEUE_LIMIT

logger = logging.getLogger(__name__)

router = APIRouter()

#: Comment frames keep proxies and load balancers from closing an idle stream.
HEARTBEAT_SECONDS = 15.0

#: One console's backlog. Past this it drops its oldest events and keeps the
#: newest — a console that fell behind wants the present, not the history.
QUEUE_LIMIT = _QUEUE_LIMIT


def _state(request: Request):
    return request.app.state.saathi


def _runner(request: Request):
    return _state(request).runner


# ---------------------------------------------------------------- the stream


def _frame(event) -> str:
    return f"event: {event.kind}\ndata: {json.dumps(event.to_json())}\n\n"


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    """Server-sent events: every real thing the world does, as it happens.

    The replay buffer goes out first so a console that connects mid-demo opens
    with context rather than a blank activity log.
    """
    state = _state(request)
    bus = state.bus

    async def events() -> AsyncIterator[str]:
        # Starlette cancels this task when the client goes away, and the
        # subscription is released in `subscribe`'s finally. Polling
        # `request.is_disconnected()` on top of that buys nothing and blocks
        # forever under an ASGI test transport, so the cancel is the only
        # teardown path here.
        async with bus.subscribe() as queue:
            for event in bus.recent(40):
                yield _frame(event)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield _frame(event)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Tells nginx and friends not to buffer; without it the stream
            # arrives in one lump at the end, which is the opposite of live.
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------- the clock


@router.get("/live")
async def live_snapshot(request: Request) -> dict:
    return _runner(request).snapshot()


class ControlRequest(BaseModel):
    action: str = Field(description="play | pause | step | reset | speed")
    seconds_per_day: float | None = None


@router.post("/live/control")
async def control(request: Request, body: ControlRequest) -> dict:
    runner = _runner(request)
    match body.action:
        case "play":
            await runner.play()
        case "pause":
            await runner.pause()
        case "step":
            # One day, on demand. Useful on stage: advance exactly when you are
            # ready to talk about what changes.
            await runner.tick()
        case "reset":
            await runner.reset()
        case "speed":
            if body.seconds_per_day is None:
                raise HTTPException(422, "speed needs seconds_per_day")
            await runner.set_speed(body.seconds_per_day)
        case _:
            raise HTTPException(422, f"unknown action {body.action!r}")
    return runner.snapshot()


# ---------------------------------------------------------------- the desk


@router.get("/desk/queue")
async def desk_queue(request: Request) -> list[dict]:
    return [c.to_json() for c in _state(request).world.pending_candidates()]


class ConfirmRequest(BaseModel):
    candidate_id: str


@router.post("/desk/confirm")
async def desk_confirm(request: Request, body: ConfirmRequest) -> dict:
    """A human confirming a record. The only way a report becomes available."""
    ok = await _runner(request).confirm(body.candidate_id, automatic=False)
    if not ok:
        raise HTTPException(404, "no such candidate, or it was already confirmed")
    return {"confirmed": True}


# ---------------------------------------------------------------- the family


class InjectRequest(BaseModel):
    patient_id: str
    #: clinical_question | logistics_question | chasing
    kind: str | None = None
    #: Supplied when a person typed the message instead of the actor writing it.
    text: str | None = None


@router.post("/live/inject")
async def inject(request: Request, body: InjectRequest) -> dict:
    """Put a message in a family's mouth and let the real guard read it.

    Nothing downstream knows this was staged: `guard.screen_inbound` runs, and a
    clinical question raises a real alert exactly as it would at 3am.
    """
    record = await _runner(request).receive_inbound(
        body.patient_id, kind=body.kind, text=body.text
    )
    if record is None:
        raise HTTPException(
            503, "no message produced — unknown patient, or actors are not configured"
        )
    return record.to_json()


@router.get("/inbound")
async def inbound(request: Request, patient_id: str | None = None) -> list[dict]:
    rows = _runner(request).inbound
    if patient_id:
        rows = [r for r in rows if r.patient_id == patient_id]
    return [r.to_json() for r in rows[-50:]]


# ---------------------------------------------------------------- the actors


@router.get("/patients/{patient_id}/brief")
async def call_brief(request: Request, patient_id: str) -> dict:
    """Four lines to read before dialling, each citing a row that exists."""
    state = _state(request)
    actors = state.runner.actors
    patient = state.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")
    if actors is None:
        return {"available": False, "lines": [], "reason": "GROQ_API_KEY not set"}

    lines = await actors.call_prep_brief(
        patient=patient,
        plan_run=state.runner.plans.get(patient_id),
        steps=state.world.steps_for(patient_id),
        ledger=state.ledger,
        alerts=state.alerts,
        inbound=state.runner.inbound,
    )
    if lines is None:
        return {"available": False, "lines": [], "reason": "brief could not be produced"}
    return {"available": True, "lines": lines, "model": actors.describe()}


class NarrationRequest(BaseModel):
    #: The trace exactly as the console is showing it: {id, text} per node.
    nodes: list[dict]


@router.post("/patients/{patient_id}/narration")
async def narration(request: Request, patient_id: str, body: NarrationRequest) -> dict:
    """Say the on-screen explanation in the family's language.

    The console sends what it is displaying, so there is one source of truth for
    the trace. Every line comes back through `guard.check_outbound` against this
    patient's current plan, and a line that fails is marked held rather than
    dropped — the navigator needs to know it is missing.
    """
    state = _state(request)
    actors = state.runner.actors
    patient = state.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")
    if actors is None:
        return {"available": False, "nodes": [], "reason": "GROQ_API_KEY not set"}

    nodes = await actors.narrate_trace(
        nodes=body.nodes,
        patient=patient,
        plan_run=state.runner.plans.get(patient_id),
        ledger=state.ledger,
    )
    if nodes is None:
        return {"available": False, "nodes": [], "reason": "narration could not be produced"}
    return {
        "available": True,
        "nodes": nodes,
        "language": patient.language.value,
        "model": actors.describe(),
    }


# ---------------------------------------------------------------- lifecycle


async def start_runner(app_state) -> None:
    """Called from the app lifespan. Autostart is opt-in."""
    await app_state.runner.start()
    if app_state.settings.live_autostart:
        await app_state.runner.play()


async def stop_runner(app_state) -> None:
    with contextlib.suppress(Exception):
        await app_state.runner.stop()


__all__ = ["router", "start_runner", "stop_runner"]
