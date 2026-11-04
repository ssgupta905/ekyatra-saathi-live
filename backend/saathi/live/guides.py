"""A family's journey guide, computed from what the runner already holds."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..domain.guide import JourneyGuide
from ..domain.pathway import get_pathway
from ..guide import build_guide
from ..orchestrator import DEFAULT_STAY_HOURS, needs_for

if TYPE_CHECKING:
    from .runner import LiveRunner


async def compute_guide(runner: LiveRunner, patient_id: str) -> JourneyGuide | None:
    patient = runner.world.patient(patient_id)
    if patient is None:
        return None
    run = runner.plans.get(patient_id)
    pathway = get_pathway(patient.pathway_id)
    hours = await asyncio.to_thread(runner.journey_hours, patient)
    policy = runner.planner.rules_for(patient.hospital_id)
    needs = needs_for(
        pathway,
        runner.world.target_kind_for(patient_id),
        round_trip_hours=hours,
        stay_threshold_hours=policy.stay_rather_than_travel_hours if policy else DEFAULT_STAY_HOURS,
    )
    return build_guide(
        patient_id=patient_id,
        pathway=pathway,
        steps=runner.world.steps_for(patient_id),
        plan=run.plan if run else None,
        items=runner.world.readiness_for(patient_id),
        needs=needs,
    )
