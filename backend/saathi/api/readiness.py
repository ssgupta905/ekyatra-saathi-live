"""What the other parties have said about a family's journey.

A ride, a stay, a pharmacy, an insurer, a booked slot: each answers one question,
"is your part ready?". This is where a desk (or, from step 5, a partner's
callback) records the answer. Recording it re-plans the family at once, so the
verdict a caller reads next already reflects it.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..domain.enums import ReadinessKind, ReadinessStatus, SourceSystem
from ..domain.models import ReadinessItem
from .access import DeskWork
from .deps import ContainerDep

router = APIRouter(tags=["readiness"])


class ReadinessIn(BaseModel):
    id: str | None = Field(default=None, description="Defaults to `<patient>-<kind>`.")
    step_id: str | None = None
    kind: ReadinessKind
    party: str = Field(min_length=1, max_length=80)
    status: ReadinessStatus
    ready_by: date | None = None
    detail: str = Field(default="", max_length=200)
    alternative_available: bool = False
    source: SourceSystem = SourceSystem.NAVIGATOR


@router.get("/patients/{patient_id}/readiness")
async def list_readiness(state: ContainerDep, patient_id: str) -> dict:
    if state.world.patient(patient_id) is None:
        raise HTTPException(404, "unknown patient")
    run = state.runner.plans.get(patient_id)
    return {
        "patient_id": patient_id,
        "decision": run.decision.value if run and run.decision else None,
        "items": [i.model_dump(mode="json") for i in state.world.readiness_for(patient_id)],
    }


@router.put("/patients/{patient_id}/readiness", dependencies=[DeskWork])
async def set_readiness(state: ContainerDep, patient_id: str, body: ReadinessIn) -> dict:
    item = ReadinessItem(
        id=body.id or f"{patient_id}-{body.kind.value}",
        patient_id=patient_id,
        step_id=body.step_id,
        kind=body.kind,
        party=body.party,
        status=body.status,
        ready_by=body.ready_by,
        detail=body.detail,
        alternative_available=body.alternative_available,
        source=body.source,
    )
    try:
        state.world.set_readiness_item(item)
    except LookupError as exc:
        raise HTTPException(404, "unknown patient") from exc
    run = await state.runner.plan_patient(patient_id, allow_render=True)
    return {
        "item": item.model_dump(mode="json"),
        "decision": run.decision.value if run and run.decision else None,
        "rationale": run.plan.rationale if run and run.plan else "",
    }


@router.delete("/patients/{patient_id}/readiness/{item_id}", dependencies=[DeskWork])
async def clear_readiness(state: ContainerDep, patient_id: str, item_id: str) -> dict:
    if not state.world.remove_readiness_item(patient_id, item_id):
        raise HTTPException(404, "no such readiness item")
    run = await state.runner.plan_patient(patient_id, allow_render=True)
    return {"decision": run.decision.value if run and run.decision else None}
