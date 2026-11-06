"""What a cab firm, a hotel desk or a pharmacy sees, and the one thing it does.

A partner is not staff. It signs in with a password like staff do, and that is
where the resemblance ends: it sees the jobs its own organisation has been
asked to do and nothing else — no families, no care steps, no plan, no other
organisation's work. `Role.PARTNER` is deliberately outside `STAFF_ROLES`, so
every endpoint guarded by `AnyStaff` already refuses it without being told to.

A job carries the least that lets someone do it: a first name, the district to
collect from, the day when the plan actually promises one, and which need it
is. Contact details are not in that list unless the family has agreed to share
them for coordinating their care — and when they have not, the job says so
plainly rather than leaving a driver to wonder.

Three answers, because three is what a vendor actually gives: *accepted* (we
have it), *ready* (it is arranged) and *cannot* (find someone else). The last
one is what drives a journey into REPLAN, where a person decides what happens
next — which is the same path a simulated organisation takes when it refuses.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..domain.consent import ConsentPurpose
from ..domain.enums import ReadinessStatus, Role
from ..domain.models import ReadinessItem
from .access import PrincipalDep, require
from .deps import ContainerDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/partner", tags=["partner"])

PartnerOnly = require(Role.PARTNER)

#: What a partner is told about the family. Nothing clinical, and no more of
#: the name than it takes to greet someone at a door.
_ANSWERS = {
    "accepted": ReadinessStatus.PENDING,
    "ready": ReadinessStatus.READY,
    "cannot": ReadinessStatus.BLOCKED,
}


class Answer(BaseModel):
    answer: Literal["accepted", "ready", "cannot"]
    #: Why not, in the vendor's own words. Asked for on "cannot" because a
    #: navigator about to book someone else needs to know what went wrong.
    reason: str = Field(default="", max_length=200)


def _organisation(container, principal) -> str:
    org = getattr(principal, "organisation_id", None)
    if not org:
        # An account that answers for nobody must see nothing. Failing closed
        # here is the difference between "no jobs" and "everybody's jobs".
        raise HTTPException(403, "this account is not linked to an organisation")
    return org


def _may_share_contact(container, patient) -> bool:
    """Has this family agreed to their details being shared to arrange care?"""
    registry = getattr(container, "consent", None)
    if registry is None or not patient.abha_number:
        return False
    try:
        return bool(
            registry.active_grants(patient.abha_number, ConsentPurpose.CARE_COORDINATION)
        )
    except Exception:  # noqa: BLE001 - a consent lookup must never leak details
        logger.exception("consent lookup failed; treating as no permission")
        return False


def _job(container, patient_id: str, item: ReadinessItem) -> dict | None:
    patient = container.world.patient(patient_id)
    if patient is None:
        return None
    run = container.runner.plans.get(patient_id)
    plan = run.plan if run else None
    shareable = _may_share_contact(container, patient)
    # A first name only. A driver needs to know who to greet, not who is ill.
    first = (patient.name or "").split(" ")[0]
    return {
        "item_id": item.id,
        "need": item.kind.value,
        "status": item.status.value,
        "detail": item.detail,
        "family": {
            "first_name": first or "the family",
            "district": patient.home_district,
            # Promised dates only. A partner told "Thursday" when the family
            # has not been told anything will arrange a car nobody comes for.
            "on": plan.travel_on.isoformat() if plan and plan.travel_on else None,
            "contact": patient.caregiver_phone if shareable else None,
            "contact_withheld": not shareable,
        },
    }


@router.get("/jobs", dependencies=[PartnerOnly])
async def jobs(container: ContainerDep, principal: PrincipalDep) -> dict:
    """Every job this organisation has been asked to do."""
    organisation = _organisation(container, principal)
    org = next(
        (o for o in container.registry.organisations() if o.id == organisation), None
    )
    open_jobs = []
    for patient in container.world.patients():
        for item in container.world.readiness_for(patient.id):
            if item.partner_id != organisation:
                continue
            job = _job(container, patient.id, item)
            if job is not None:
                open_jobs.append(job)
    # Waiting first: those are the ones somebody is expecting an answer to.
    open_jobs.sort(key=lambda j: (j["status"] != "pending", j["item_id"]))
    return {
        "organisation": {"id": organisation, "name": org.name if org else organisation},
        "jobs": open_jobs,
    }


@router.post("/jobs/{item_id}", dependencies=[PartnerOnly])
async def answer(
    container: ContainerDep,
    principal: PrincipalDep,
    item_id: str,
    body: Annotated[Answer, ...],
) -> dict:
    """The vendor's own answer. Re-plans the family it belongs to."""
    organisation = _organisation(container, principal)
    found: tuple[str, ReadinessItem] | None = None
    for patient in container.world.patients():
        for item in container.world.readiness_for(patient.id):
            if item.id == item_id:
                found = (patient.id, item)
                break
        if found:
            break
    if found is None:
        raise HTTPException(404, "no such job")
    patient_id, item = found
    if item.partner_id != organisation:
        # Not "forbidden": a partner should not be able to learn that a job
        # exists for somebody else by the shape of the refusal.
        raise HTTPException(404, "no such job")

    if body.answer == "cannot" and not body.reason.strip():
        raise HTTPException(422, "say what went wrong, so someone can book another")

    status = _ANSWERS[body.answer]
    detail = {
        "accepted": f"{principal.name} has it",
        "ready": f"confirmed by {principal.name}",
        "cannot": f"{principal.name} cannot: {body.reason.strip()}",
    }[body.answer]
    updated = container.world.set_readiness_item(
        item.model_copy(update={"status": status, "detail": detail, "due_at": None})
    )
    await container.runner.plan_patient(patient_id, allow_render=True)
    return {"item_id": updated.id, "status": updated.status.value, "detail": updated.detail}


__all__ = ["router"]
