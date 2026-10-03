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
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..domain.enums import DisruptionKind, Role
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
    action: str = Field(description="play | pause | step | reset | speed | advance_story")
    seconds_per_day: float | None = None
    #: For action="advance_story": which scripted story to advance.
    story: str | None = None


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
        case "advance_story":
            if not body.story:
                raise HTTPException(422, "advance_story needs story")
            try:
                beat = await runner.advance_story(body.story)
            except LookupError as exc:
                raise HTTPException(404, str(exc)) from exc
            return {**runner.snapshot(), "story_beat": beat}
        case _:
            raise HTTPException(422, f"unknown action {body.action!r}")
    return runner.snapshot()


# ---------------------------------------------------------------- the stories


@router.get("/story")
async def story_state(request: Request) -> dict:
    """Which stories exist, where each has got to, and who acts next.

    The console's story bar renders from this rather than carrying its own copy
    of the brief's table, so the beats cannot drift out of step with what
    `advance_story` will actually run.
    """
    return _runner(request).story_state()


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


# ---------------------------------------------------------------- disruptions


class DisruptionRequest(BaseModel):
    resource_id: str
    kind: DisruptionKind
    unavailable_from: date
    unavailable_to: date | None = None
    note: str = ""


class WorkLogRequest(BaseModel):
    """A line a department already writes, rather than a form it has to fill."""

    text: str = Field(min_length=3, max_length=600)


#: Words a desk actually uses, for when no model is available. Deliberately
#: thin: this is a fallback that says so, not a parser pretending to be one.
_KIND_WORDS: dict[DisruptionKind, tuple[str, ...]] = {
    DisruptionKind.MACHINE_DOWN: ("down", "broken", "out of service", "fault", "not working"),
    DisruptionKind.STAFF_UNAVAILABLE: ("leave", "away", "absent", "off", "unavailable", "called"),
    DisruptionKind.STOCK_DELAY: ("stock", "delivery", "supply", "late", "shipment", "not arrived"),
}


def _read_without_a_model(text: str, resources, today: date) -> dict | None:
    """Match a resource by name and a kind by vocabulary. Nothing clever.

    Exists so the desk's free-text box still does something with no credentials
    present — invariant 9 — and it reports itself as a pattern match so nobody
    mistakes it for the model having read the line.
    """
    lowered = text.lower()
    hit = None
    for resource in resources:
        words = [resource.id.lower(), *resource.display_name.lower().split()]
        if any(len(w) > 3 and w in lowered for w in words):
            hit = resource
            break
    if hit is None:
        return None

    kind = next(
        (k for k, words in _KIND_WORDS.items() if any(w in lowered for w in words)),
        DisruptionKind.MACHINE_DOWN,
    )
    return {
        "resource_id": hit.id,
        "kind": kind.value,
        "unavailable_from": today.isoformat(),
        "unavailable_to": "",
        "confidence": "low",
        "read_as": f"matched the words in this line to {hit.display_name}",
    }


@router.post("/disruptions/read")
async def read_work_log(request: Request, body: WorkLogRequest) -> dict:
    """Read a department's own words and propose the outage they describe.

    Proposes. It does not raise anything. A desk thinks "MRI-2 down till
    Saturday", not `resource_id` and `unavailable_to`, so this takes the line
    they would write in a log they already keep and hands back what it
    understood — for them to confirm or correct. The model supplies a reading;
    a person still supplies the decision, which is invariant 3 and the reason
    this is a separate endpoint from the one that acts.
    """
    state = _state(request)
    resources = list(state.world.resources.values())
    if not resources:
        raise HTTPException(409, "no resources are registered to report against")

    today = state.world.today
    reading = None
    read_by = "pattern match"
    if state.runner.actors is not None:
        async with state.runner.working(
            "Reading the work log", detail="proposing an outage for a desk to confirm"
        ):
            reading = await state.runner.actors.read_work_log(body.text, resources, today)
        if reading is not None:
            state.runner._bump("actor_calls")
            read_by = state.runner.actors.describe()

    if reading is None:
        reading = _read_without_a_model(body.text, resources, today)
    if reading is None:
        return {
            "understood": False,
            "reason": "nothing in that line names a resource this hospital can report on",
            "resources": [
                {"id": r.id, "display_name": r.display_name, "kind": r.kind.value}
                for r in resources
            ],
        }

    resource = state.world.resources.get(reading["resource_id"])
    return {
        "understood": True,
        "resource_id": reading["resource_id"],
        "resource_name": resource.display_name if resource else reading["resource_id"],
        "kind": reading["kind"],
        "unavailable_from": reading["unavailable_from"],
        "unavailable_to": reading.get("unavailable_to") or None,
        "confidence": reading.get("confidence", "low"),
        #: What it took the line to mean, in a sentence, so the desk is
        #: confirming an understanding rather than a row of fields.
        "read_as": reading.get("read_as", ""),
        "read_by": read_by,
        "note": body.text.strip(),
    }


@router.post("/disruptions")
async def raise_disruption(request: Request, body: DisruptionRequest) -> dict:
    """A desk's one-tap report. Everything downstream — the holding message,
    the re-solve, the options — happens because the runner reacted to this,
    not because this endpoint decided anything."""
    disruption, affected = await _runner(request).raise_disruption(
        resource_id=body.resource_id,
        kind=body.kind,
        unavailable_from=body.unavailable_from,
        unavailable_to=body.unavailable_to,
        note=body.note,
    )
    return {"disruption": disruption.model_dump(mode="json"), "affected_patient_ids": affected}


@router.get("/disruptions")
async def list_disruptions(request: Request) -> list[dict]:
    return [d.model_dump(mode="json") for d in _state(request).world.open_disruptions()]


@router.get("/disruptions/pending")
async def pending_options(request: Request) -> list[dict]:
    """Every option set currently waiting on a human — the navigator's and
    doctor's call list for the disruption loop, without needing to already
    know a disruption or patient id."""
    runner = _runner(request)
    rows = []
    for option_set in runner.options.values():
        requires_doctor = any(
            runner.touches_treatment(option) for option in option_set.options
        )
        rows.append(
            {
                "patient_id": option_set.patient_id,
                "disruption_id": option_set.disruption_id,
                "option_count": len(option_set.options),
                "requires_doctor": requires_doctor,
                "created_at": option_set.created_at.isoformat(),
            }
        )
    return rows


@router.get("/disruptions/{disruption_id}/options/{patient_id}")
async def disruption_options(request: Request, disruption_id: str, patient_id: str) -> dict:
    """Ranked options for one patient. Order is the only ranking — there is
    no score field anywhere in the response."""
    option_set = _runner(request).options.get(patient_id)
    if option_set is None or option_set.disruption_id != disruption_id:
        return {"options": []}
    return option_set.to_json()


class ApproveRequest(BaseModel):
    patient_id: str
    option_index: int
    approved_by_role: Role
    approved_by: str


@router.post("/disruptions/{disruption_id}/approve")
async def approve_disruption_option(
    request: Request, disruption_id: str, body: ApproveRequest
) -> dict:
    """The brief's single approval action. A navigator approving an option
    that touches treatment or dose timing is rejected — structurally, not
    by a UI hint — exactly as the model's own travel decision is bound."""
    try:
        approval = await _runner(request).approve_option(
            patient_id=body.patient_id,
            option_index=body.option_index,
            approved_by_role=body.approved_by_role,
            approved_by=body.approved_by,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    return approval.model_dump(mode="json")


class IVRConfirmRequest(BaseModel):
    confirmation_id: str
    digit: str


@router.post("/live/ivr-confirm")
async def ivr_confirm(request: Request, body: IVRConfirmRequest) -> dict:
    """The family's own "press 1" — logged like any other fact. In the
    credential-free live demo this is a simulated digit press, never a real
    Exotel callback."""
    ok = await _runner(request).confirm_ivr(body.confirmation_id, body.digit)
    if not ok:
        raise HTTPException(404, "no such confirmation, or it was already confirmed")
    return {"confirmed": True}


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
