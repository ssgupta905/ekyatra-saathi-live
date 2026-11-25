"""Near you: where a family could get what the journey needs, close to where they will be.

Suggestions from a map service, not partners. Only a place and a generic word
go to it; nothing about the family. A place that has not answered is never said
to have anything in stock.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from ..domain.places import KINDS_FOR_NEED
from ..orchestrator.nearby_needs import rank
from ..ports.places import PlacesUnavailable
from .access import FamilyOrStaff
from .deps import ContainerDep

router = APIRouter(tags=["nearby"])


@router.get("/patients/{patient_id}/nearby", dependencies=[FamilyOrStaff])
async def nearby(
    state: ContainerDep,
    patient_id: str,
    need: Literal["medicine", "tests", "equipment", "clinic"],
    near: Literal["hospital", "home", "place"] = "hospital",
    place: str = Query(default="", max_length=200),
    at: datetime | None = None,
) -> dict:
    patient = state.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")
    finder = state.places
    if finder is None:
        raise HTTPException(409, "no map service is set up here")

    if near == "hospital":
        hospital = next(
            (h for h in (state.registry.hospitals() if state.registry else []) if h.id == patient.hospital_id),
            None,
        )
        if hospital is None or hospital.latitude is None or hospital.longitude is None:
            raise HTTPException(409, "the hospital's entrance is not on record")
        centre = (hospital.latitude, hospital.longitude)
    else:
        name = patient.home_district if near == "home" else place.strip()
        if not name:
            raise HTTPException(422, "say where")
        tools = state.runner.tools
        hit = None
        if tools is not None:
            try:
                hit = await asyncio.to_thread(tools.geo.geocode, name)
            except Exception:  # noqa: BLE001 - an unplaceable name is "say where", not a crash
                hit = None
        if hit is None:
            raise HTTPException(422, "could not find that place on a map")
        centre = (hit.lat, hit.lon)

    # A family who has told us they have a limit wants the cheaper kind first.
    desk = state.runner.kharcha
    tight = bool(desk and desk.store.limit(patient_id) is not None)

    try:
        batches = await asyncio.gather(
            *[
                finder.nearby(kind, centre[0], centre[1], language=patient.language or "en")
                for kind in KINDS_FOR_NEED[need]
            ]
        )
    except PlacesUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    found = rank([p for batch in batches for p in batch], near=centre, at=at or datetime.now(UTC), money_is_tight=tight)
    return {
        "need": need,
        "near": near,
        "source": finder.name,
        "places": [r.model_dump(mode="json") for r in found],
    }
