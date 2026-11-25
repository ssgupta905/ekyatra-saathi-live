"""How to get there: which bus, boarded where, and which way suits this family.

Family only, like the books it reads: the answer weighs what the family said
they can manage. The place a family types for the last leg is sent to the route
service for this one request and is not kept.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from ..domain.itinerary import FareBasis, RouteOption
from ..orchestrator.trip_options import weigh
from ..ports.routes import Place, RoutesUnavailable
from .access import FamilyOnly
from .deps import ContainerDep

router = APIRouter(tags=["trip"])


def _room(state, patient_id: str) -> int | None:
    """What of the family's own monthly limit is still free this month. None when none was said."""
    desk = state.runner.kharcha
    if desk is None:
        return None
    limit = desk.store.limit(patient_id)
    if limit is None:
        return None
    this_month, _ = desk.months(patient_id)
    return max(limit.monthly_paise - this_month.total_known_paise, 0)


@router.get("/patients/{patient_id}/trip/options", dependencies=[FamilyOnly])
async def options(
    state: ContainerDep,
    patient_id: str,
    leg: Literal["far", "near"] = "far",
    origin: str = Query(default="", max_length=200),
    arrive_by: datetime | None = None,
) -> dict:
    patient = state.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")
    planner = state.routes
    if planner is None:
        raise HTTPException(409, "no route service is set up here")
    hospital = next(
        (
            h
            for h in (state.registry.hospitals() if state.registry else [])
            if h.id == patient.hospital_id
        ),
        None,
    )
    if hospital is None or hospital.latitude is None or hospital.longitude is None:
        raise HTTPException(409, "the hospital's entrance is not on record")
    start = patient.home_district if leg == "far" else origin.strip()
    if not start:
        raise HTTPException(422, "say where you are starting from")

    to = Place(f"{hospital.latitude},{hospital.longitude}")
    try:
        transit, driving = await asyncio.gather(
            planner.options(Place(start), to, mode="transit", arrive_by=arrive_by),
            planner.options(Place(start), to, mode="driving"),
        )
    except RoutesUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    # A seller's firm price for a car is the family's to book: it is the only
    # cost a car option may carry, with its owner named.
    quoted = next(
        (b["amount_paise"]
         for b in (state.runner.network.bookable(patient_id) if state.runner.network else [])
         if b.get("amount_paise")),
        None,
    )
    cars: list[RouteOption] = [
        o.model_copy(update={"fare_paise": quoted, "fare_basis": FareBasis.QUOTE})
        if quoted and leg == "near"
        else o
        for o in driving[:1]
    ]
    guidance = weigh(transit[:4] + cars, room_paise=_room(state, patient_id), arrive_by=arrive_by)
    return {
        "leg": leg,
        "source": planner.name,
        "guidance": guidance.model_dump(mode="json"),
    }
