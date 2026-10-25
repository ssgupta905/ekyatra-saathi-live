"""HTTP surface.

Three audiences: the navigator console, the hospital's systems, and the
messaging webhooks. Routes stay thin — all logic lives in the planner.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..domain.enums import AlertKind, Channel, Decision, Language, SourceSystem, StepKind
from ..domain.models import Alert, CareStep, Patient, VisitPlan
from ..engagement.pelt import detect_disengagement
from ..language import guard
from ..synthetic.generate import QUEUE_PROFILES, evaluate
from .access import AdminOnly, AnyStaff, FamilyOrStaff, PrincipalDep
from .deps import ContainerDep

router = APIRouter()



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
async def health(state: ContainerDep) -> dict:
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
async def list_patients(state: ContainerDep, principal: PrincipalDep) -> list[Patient]:
    """Every family, for staff; a caregiver's own, for a caregiver."""
    patients = list(state.cohort.patients)
    if principal is None or principal.is_staff:
        return patients
    return [p for p in patients if principal.may_see(p.id)]


@router.get(
    "/patients/{patient_id}/steps",
    response_model=list[CareStep],
    dependencies=[FamilyOrStaff],
)
async def patient_steps(state: ContainerDep, patient_id: str) -> list[CareStep]:
    if state.patient(patient_id) is None:
        raise HTTPException(404, "unknown patient")
    return list(state.steps_for(patient_id))


@router.post("/plan", response_model=PlanResponse, dependencies=[AnyStaff])
async def plan(state: ContainerDep, body: PlanRequest, recompute: bool = False) -> PlanResponse:
    """The current plan for this patient.

    By default this *reads* the runner's latest real planning run rather than
    planning on request. In a live world the console must reflect the world, not
    cause it — a navigator opening a family should not be the reason its ledger
    grows. `?recompute=true` forces a fresh run for scripted use and tests.
    """
    patient = state.patient(body.patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")

    run = state.runner.plans.get(body.patient_id)
    if recompute or run is None or body.today is not None:
        # Planning can include a blocking LLM call; keep it off the event loop.
        result = await asyncio.to_thread(
            state.planner.plan_visit,
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


@router.post("/engagement/check", response_model=Alert | None, dependencies=[AnyStaff])
async def engagement_check(state: ContainerDep, body: EngagementRequest) -> Alert | None:
    """Run PELT over a caregiver's reply latencies and raise an alert on a shift."""
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


@router.get("/alerts", response_model=list[Alert], dependencies=[AnyStaff])
async def list_alerts(state: ContainerDep) -> list[Alert]:
    return list(state.alerts)


class InboundMessage(BaseModel):
    patient_id: str
    text: str


class InboundVerdict(BaseModel):
    answerable: bool
    reason: str | None = None
    triggers: list[str] = []


@router.post("/messages/inbound", response_model=InboundVerdict, dependencies=[AnyStaff])
async def inbound(state: ContainerDep, body: InboundMessage) -> InboundVerdict:
    """Screen a caregiver's message. Clinical questions go to a human, always."""
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


@router.get("/admin/config", dependencies=[AdminOnly])
async def admin_config(state: ContainerDep) -> dict:
    """The admin's read-only view of the readiness rules, languages and
    channels the system runs with. Surfaces real settings — no field here is
    invented for the console; it is what `Settings` and `QUEUE_PROFILES`
    already hold.
    """
    settings = state.settings
    return {
        "readiness": {
            "conformal_alpha": settings.conformal_alpha,
            "coverage": 1 - settings.conformal_alpha,
            "queue_turnaround_profiles": {
                queue: {
                    "median_days": median,
                    "tail_probability": tail_p,
                    "tail_extra_days": tail_extra,
                }
                for queue, (median, tail_p, tail_extra) in QUEUE_PROFILES.items()
            },
        },
        "staff": {
            "watched_families": settings.live_watched,
            "auto_confirm_ticks": settings.live_auto_confirm_ticks,
            "inbound_every_seconds": settings.live_inbound_every_seconds,
        },
        "languages": [lang.value for lang in Language],
        "channels": [channel.value for channel in Channel],
        "language_layer_enabled": settings.language_layer_enabled,
        "actors_enabled": settings.actors_enabled,
    }


@router.get("/ledger", dependencies=[AdminOnly])
async def ledger_all(
    state: ContainerDep,
    source: SourceSystem | None = None,
    since: datetime | None = None,
    patient_id: str | None = None,
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """The admin audit log: every action across every patient, newest first.

    Read-only, like the per-patient view — opening this page cannot grow the
    ledger any more than opening a family's page can. `q` matches the claim or
    the record id; `total` is the count before paging.
    """
    entries = list(state.ledger.all_entries(source=source, since=since))
    if patient_id:
        entries = [e for e in entries if e.patient_id == patient_id]
    if q:
        needle = q.lower()
        entries = [
            e for e in entries if needle in e.claim.lower() or needle in e.source_record_id.lower()
        ]
    entries.reverse()
    page = entries[offset : offset + limit]
    return {
        "intact": state.ledger.verify(),
        "total": len(entries),
        "offset": offset,
        "limit": limit,
        "entries": [
            {
                "id": e.id,
                "patient_id": e.patient_id,
                "source": e.source.value,
                "source_record_id": e.source_record_id,
                "claim": e.claim,
                "recorded_at": e.recorded_at.isoformat(),
                "entry_hash": e.entry_hash[:12],
                "metadata": e.metadata,
            }
            for e in page
        ],
    }


@router.get("/ledger/{patient_id}", dependencies=[AnyStaff])
async def ledger_for_patient(state: ContainerDep, patient_id: str) -> dict:
    """Everything Saathi has asserted about this patient, and its provenance."""
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


@router.get("/metrics", dependencies=[AnyStaff])
async def metrics(state: ContainerDep, recompute: bool = False) -> dict:
    """Score the cohort against planted ground truth.

    The runner rescores on every change, so this normally reads that result.
    `?recompute=true` re-plans the whole cohort from scratch.
    """
    if not recompute and state.runner.metrics:
        return state.runner.metrics

    def replan_cohort() -> dict[str, date | None]:
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
        return decisions

    # A whole-cohort replan is long and may call a language model: off the loop.
    decisions = await asyncio.to_thread(replan_cohort)
    return evaluate(state.cohort, decisions)
