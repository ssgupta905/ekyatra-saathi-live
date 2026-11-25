"""The journey guide as the apps read it: one family's chain, and everyone's at once.

The guide is derived on every read from the plan the planner already made and
what every other party has said, so it can never disagree with the verdict.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..domain.guide import JourneyGuide, StageState
from ..live.guides import compute_guide
from .access import AnyStaff, FamilyOrStaff
from .deps import ContainerDep

router = APIRouter(tags=["guide"])


async def guide_for(state: ContainerDep, patient_id: str) -> JourneyGuide | None:
    return await compute_guide(state.runner, patient_id)


def trip_for(state: ContainerDep, patient_id: str, found: JourneyGuide) -> dict | None:
    """What a ride or stay app needs to be opened on this family's trip.

    Only what the apps ask for, and nothing about the family: where the hospital's
    entrance is, and the day they arrive. The day appears only when the plan is a
    GO, like every other date a family is shown; before that the apps open with
    a destination and no date, which is all that is known.

    The pickup is never here. The ride app is told "my location" and works it
    out from the phone, so where a family is staying never passes through us.
    """
    patient = state.world.patient(patient_id)
    if patient is None or state.registry is None:
        return None
    hospital = next((h for h in state.registry.hospitals() if h.id == patient.hospital_id), None)
    if hospital is None:
        return None
    visit = next((s for s in found.stages if s.kind.value == "visit"), None)
    destination = None
    if hospital.latitude is not None and hospital.longitude is not None:
        destination = {
            "name": hospital.name,
            "latitude": hospital.latitude,
            "longitude": hospital.longitude,
            "address": hospital.address or f"{hospital.name}, {hospital.place}",
        }
    return {
        "destination": destination,
        "city": hospital.place,
        "arrive_on": visit.on.isoformat() if visit is not None and visit.on else None,
    }


def guide_json(state: ContainerDep, patient_id: str, found: JourneyGuide) -> dict:
    """The guide as the apps read it, with the trip the apps it leads to are opened on."""
    body = found.model_dump(mode="json")
    body["trip"] = trip_for(state, patient_id, found)
    return body


@router.get("/patients/{patient_id}/guide", dependencies=[FamilyOrStaff])
async def guide(state: ContainerDep, patient_id: str) -> dict:
    found = await guide_for(state, patient_id)
    if found is None:
        raise HTTPException(404, "unknown patient")
    return guide_json(state, patient_id, found)


@router.get("/network", dependencies=[AnyStaff])
async def network(state: ContainerDep) -> dict:
    """Every family against every stage: who holds each journey, and which are stuck."""
    rows = []
    for patient in state.world.patients():
        found = await guide_for(state, patient.id)
        if found is None or not found.stages:
            continue
        rows.append(
            {
                "patient_id": patient.id,
                "name": patient.name or patient.id,
                "district": patient.home_district,
                "pathway_id": patient.pathway_id,
                "decision": found.decision,
                "now": found.now_stage_id,
                "done": found.done,
                "total": found.total,
                "stages": [
                    {
                        "kind": s.kind.value,
                        "state": s.state.value,
                        "party": s.party,
                        "detail": s.detail,
                    }
                    for s in found.stages
                ],
                "stuck": any(s.state is StageState.PROBLEM for s in found.stages),
            }
        )
    rows.sort(key=lambda r: (not r["stuck"], r["done"] / max(r["total"], 1)))
    parties: dict[str, dict[str, int]] = {}
    for row in rows:
        for stage in row["stages"]:
            if stage["party"] and stage["state"] != "done":
                counts = parties.setdefault(stage["party"], {"waiting": 0, "problem": 0})
                counts["problem" if stage["state"] == "problem" else "waiting"] += 1
    return {
        "families": rows,
        "parties": [{"party": p, **c} for p, c in sorted(parties.items())],
    }
