"""Load, or reset, three scripted families for a walk-through.

For an administrator, on real records. Nothing about who receives a sign-in code
is stored in the code: the addresses are given here, by whoever is demonstrating.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..bootstrap.demo_cast import build_cast
from ..bootstrap.demo_profiles import seed_demo_onboarding
from .access import AdminOnly, PrincipalDep
from .deps import ContainerDep
from .registry import ledger

router = APIRouter(tags=["demo"])


class CastIn(BaseModel):
    #: One per family, in order: the first gets the smooth journey, the second the
    #: vendor failure, the third the dialysis story.
    emails: list[str] = Field(
        min_length=1, max_length=3, description="Where each family's sign-in code goes."
    )


@router.post("/demo/cast", dependencies=[AdminOnly])
async def load_cast(state: ContainerDep, principal: PrincipalDep, body: CastIn) -> dict:
    if not state.world.real or state.registry is None or state.onboarding is None:
        raise HTTPException(409, "the demo cast is loaded on real records")
    for email in body.emails:
        if "@" not in email or " " in email.strip():
            raise HTTPException(422, f"'{email}' is not an email address")
    cast = build_cast(body.emails, state.world.today)

    # The scripted vendor failure: Uber says it cannot, and has Ola to turn to.
    uber = next((o for o in state.registry.organisations() if o.id == "cab-uber"), None)
    if uber is not None and any(m.partners.get("transport") == "cab-uber" for m in cast):
        state.registry.save_organisation(
            uber.model_copy(update={"answer": "cannot", "alternate_id": "cab-ola"})
        )

    # Fill in each family's background first: it skips a family that already has details.
    seed_demo_onboarding(state.onboarding, tuple(m.patient for m in cast), state.registry)
    loaded = []
    for member in cast:
        patient = member.patient
        existing = state.world.patient(patient.id)
        if existing is None:
            state.world.add_patient(patient)
        else:
            state.world.update_patient(
                patient.id, **patient.model_dump(exclude={"id", "family_members"})
            )
        for step in member.steps:
            if state.world.step(step.id) is None:
                state.world.add_step(step)
            else:
                state.world.update_step(step.id, **step.model_dump(exclude={"id", "patient_id"}))
        # Start the story again: nobody has been asked, nothing has been said.
        for item in state.world.readiness_for(patient.id):
            state.world.remove_readiness_item(patient.id, item.id)
        state.runner.guides.pop(patient.id, None)
        state.onboarding.save_section(patient.id, "partners", member.partners, "demo cast")
        saved = state.onboarding.section(patient.id, "identity")
        if saved is not None:  # a reset with a new address: sign-in already follows the record
            state.onboarding.save_section(
                patient.id,
                "identity",
                {**saved[0], "caregiver_email": patient.caregiver_email},
                "demo cast",
            )
        loaded.append(patient.id)

    for member in cast:
        await state.runner.plan_patient(member.patient.id, allow_render=True)
    ledger(state, principal, "demo/cast", f"demo cast loaded: {', '.join(loaded)}")
    return {
        "families": [
            {
                "patient_id": m.patient.id,
                "name": m.patient.name,
                "email": m.patient.caregiver_email,
                "story": m.story,
            }
            for m in cast
        ]
    }
