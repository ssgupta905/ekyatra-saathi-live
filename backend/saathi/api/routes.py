"""HTTP surface.

Three audiences: the navigator console, the hospital's systems, and the
messaging webhooks. Routes stay thin — all logic lives in the planner.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..domain.enums import AlertKind, Decision, StepKind
from ..domain.models import Alert, CareStep, Patient, VisitPlan
from ..engagement.pelt import detect_disengagement
from ..language import guard
from ..synthetic.generate import evaluate

router = APIRouter()


def _state(request: Request):
    return request.app.state.saathi


class PlanRequest(BaseModel):
    patient_id: str
    target_kind: StepKind = StepKind.REVIEW_CONSULT
    today: date | None = None


class PlanResponse(BaseModel):
    plan: VisitPlan | None
    message_body: str | None = None
    routed_to_care_team: bool = False
    escalation: str | None = None
    #: Provenance of the run itself, so the console can say when this was
    #: decided and what it cost rather than implying it is instantaneous.
    computed_at: str | None = None
    sim_date: str | None = None
    plan_ms: float | None = None
    render_ms: float | None = None
    rendered_by: str | None = None


@router.get("/health")
async def health(request: Request) -> dict:
    state = _state(request)
    layer = state.planner.language_layer
    return {
        "status": "ok",
        "ledger_intact": state.ledger.verify(),
        "ledger_entries": state.ledger.size(),
        "language_layer": state.settings.language_layer_enabled,
        "language_model": layer.describe() if layer else None,
        "actors": state.runner.actors is not None,
        "patients": len(state.cohort.patients),
        "sim_date": state.world.today.isoformat(),
        "running": state.world.clock.running,
    }


@router.get("/patients", response_model=list[Patient])
async def list_patients(request: Request) -> list[Patient]:
    return list(_state(request).cohort.patients)


@router.get("/patients/{patient_id}/steps", response_model=list[CareStep])
async def patient_steps(request: Request, patient_id: str) -> list[CareStep]:
    state = _state(request)
    if state.patient(patient_id) is None:
        raise HTTPException(404, "unknown patient")
    return list(state.steps_for(patient_id))


@router.post("/plan", response_model=PlanResponse)
async def plan(request: Request, body: PlanRequest, recompute: bool = False) -> PlanResponse:
    """The current plan for this patient.

    By default this *reads* the runner's latest real planning run rather than
    planning on request. In a live world the console must reflect the world, not
    cause it — a navigator opening a family should not be the reason its ledger
    grows. `?recompute=true` forces a fresh run for scripted use and tests.
    """
    state = _state(request)
    patient = state.patient(body.patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")

    run = state.runner.plans.get(body.patient_id)
    if recompute or run is None or body.today is not None:
        result = state.planner.plan_visit(
            patient=patient,
            steps=list(state.steps_for(body.patient_id)),
            target_kind=body.target_kind,
            today=body.today,
        )
        message = result.get("message")
        return PlanResponse(
            plan=result.get("plan"),
            message_body=(
                message.body if message and not message.routed_to_care_team else None
            ),
            routed_to_care_team=bool(message and message.routed_to_care_team),
            escalation=result.get("escalation"),
        )

    message = run.message
    return PlanResponse(
        plan=run.plan,
        message_body=message.body if message and not message.routed_to_care_team else None,
        routed_to_care_team=bool(message and message.routed_to_care_team),
        escalation=run.escalation,
        computed_at=run.computed_at.isoformat(),
        sim_date=run.sim_date,
        plan_ms=run.plan_ms,
        render_ms=run.render_ms,
        rendered_by=run.rendered_by,
    )


class EngagementRequest(BaseModel):
    patient_id: str
    #: Response latencies in hours, oldest first.
    response_latency_hours: list[float]


@router.post("/engagement/check", response_model=Alert | None)
async def engagement_check(request: Request, body: EngagementRequest) -> Alert | None:
    """Run PELT over a caregiver's reply latencies and raise an alert on a shift."""
    state = _state(request)
    result = detect_disengagement(body.response_latency_hours)
    if not result.disengaged:
        return None

    alert = Alert(
        id=f"alert-{body.patient_id}-{len(state.alerts)}",
        patient_id=body.patient_id,
        kind=AlertKind.DISENGAGEMENT,
        raised_at=datetime.now(UTC),
        detail=(
            f"reply latency moved from {result.previous_segment_mean:.1f}h "
            f"to {result.last_segment_mean:.1f}h "
            f"at observation {result.change_points[-1]}"
        ),
    )
    state.alerts.append(alert)
    return alert


@router.get("/alerts", response_model=list[Alert])
async def list_alerts(request: Request) -> list[Alert]:
    return list(_state(request).alerts)


class InboundMessage(BaseModel):
    patient_id: str
    text: str


class InboundVerdict(BaseModel):
    answerable: bool
    reason: str | None = None
    triggers: list[str] = []


@router.post("/messages/inbound", response_model=InboundVerdict)
async def inbound(request: Request, body: InboundMessage) -> InboundVerdict:
    """Screen a caregiver's message. Clinical questions go to a human, always."""
    state = _state(request)
    verdict = guard.screen_inbound(body.text)
    if not verdict.allowed:
        state.alerts.append(
            Alert(
                id=f"alert-{body.patient_id}-{len(state.alerts)}",
                patient_id=body.patient_id,
                kind=AlertKind.CLINICAL_QUESTION,
                raised_at=datetime.now(UTC),
                detail=body.text[:280],
            )
        )
    return InboundVerdict(
        answerable=verdict.allowed,
        reason=verdict.reason,
        triggers=list(verdict.triggers),
    )


@router.get("/ledger/{patient_id}")
async def ledger_for_patient(request: Request, patient_id: str) -> dict:
    """Everything Saathi has asserted about this patient, and its provenance."""
    state = _state(request)
    entries = state.ledger.for_patient(patient_id)
    return {
        "intact": state.ledger.verify(),
        "entries": [
            {
                "id": e.id,
                "source": e.source.value,
                "source_record_id": e.source_record_id,
                "claim": e.claim,
                "recorded_at": e.recorded_at.isoformat(),
                "entry_hash": e.entry_hash[:12],
            }
            for e in entries
        ],
    }


@router.get("/metrics")
async def metrics(request: Request, recompute: bool = False) -> dict:
    """Score the cohort against planted ground truth.

    The runner rescores on every change, so this normally reads that result.
    `?recompute=true` re-plans the whole cohort from scratch.
    """
    state = _state(request)
    if not recompute and state.runner.metrics:
        return state.runner.metrics
    decisions: dict[str, date | None] = {}
    for patient in state.cohort.patients:
        result = state.planner.plan_visit(
            patient=patient,
            steps=list(state.steps_for(patient.id)),
            target_kind=StepKind.REVIEW_CONSULT,
        )
        plan_obj = result.get("plan")
        decisions[patient.id] = (
            plan_obj.travel_on
            if plan_obj and plan_obj.decision is Decision.GO
            else None
        )
    return evaluate(state.cohort, decisions)
