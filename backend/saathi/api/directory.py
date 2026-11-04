"""The network directory, and who may do what.

Labs, pharmacies, distributors, shops, cab services, travel partners, hotels and
insurers: the organisations a journey runs through. Read by every staff role;
changed by administrators, with a ledger row naming who.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..domain.directory import Organisation, OrgType, PartnerMode
from ..domain.enums import Role
from .access import AdminOnly, AnyStaff, PrincipalDep
from .deps import ContainerDep
from .registry import _known_hospital, _store, ledger, ledger_change

router = APIRouter()

#: What each type is called on screen, and which need on a journey it answers.
TYPE_LABELS: dict[OrgType, str] = {
    OrgType.LAB: "Lab or diagnostic centre",
    OrgType.PHARMACY: "Pharmacy",
    OrgType.MEDICINE_DISTRIBUTOR: "Medicine distributor",
    OrgType.EQUIPMENT_DISTRIBUTOR: "Medical equipment distributor",
    OrgType.SHOP: "Shop or merchant",
    OrgType.CAB: "Cab service",
    OrgType.TRAVEL: "Travel partner (rail, bus, air)",
    OrgType.HOTEL: "Hotel or stay",
    OrgType.INSURER: "Insurer or scheme desk",
    OrgType.AMBULANCE: "Ambulance",
}


@router.get("/directory/types", dependencies=[AnyStaff])
async def types() -> list[dict]:
    return [{"id": t.value, "label": label} for t, label in TYPE_LABELS.items()]


@router.get("/directory", dependencies=[AnyStaff])
async def organisations(
    state: ContainerDep, type: OrgType | None = None, q: str = "", district: str = ""
) -> list[dict]:
    wanted = q.strip().lower()
    place = district.strip().lower()
    found = []
    for org in _store(state).organisations():
        if type is not None and org.type is not type:
            continue
        if wanted and wanted not in f"{org.name} {' '.join(org.services)}".lower():
            continue
        if place and org.districts and place not in (d.lower() for d in org.districts):
            continue
        found.append(org.model_dump(mode="json"))
    return found


def _check_links(state: ContainerDep, body: Organisation) -> None:
    known = {o.id for o in _store(state).organisations()}
    for other in (*body.linked_ids, *([body.alternate_id] if body.alternate_id else [])):
        if other not in known:
            raise HTTPException(422, f"no organisation {other} in the directory")
        if other == body.id:
            raise HTTPException(422, "an organisation cannot link to itself")
    for hospital_id in body.hospital_ids:
        _known_hospital(state, hospital_id)


@router.post("/directory", status_code=201, dependencies=[AdminOnly])
async def add_organisation(
    state: ContainerDep, principal: PrincipalDep, body: Organisation
) -> dict:
    store = _store(state)
    if any(o.id == body.id for o in store.organisations()):
        raise HTTPException(409, f"organisation {body.id} already exists")
    _check_links(state, body)
    store.save_organisation(body)
    ledger(
        state,
        principal,
        f"organisation/{body.id}",
        f"{body.type.value} {body.id} added: {body.name}",
    )
    return body.model_dump(mode="json")


class OrganisationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    services: tuple[str, ...] | None = None
    districts: tuple[str, ...] | None = None
    hospital_ids: tuple[str, ...] | None = None
    address: str | None = None
    contact: str | None = None
    hours: str | None = None
    mode: PartnerMode | None = None
    answer: str | None = Field(default=None, pattern="^(ready|cannot)$")
    delay_seconds: int | None = Field(default=None, ge=0, le=3600)
    alternate_id: str | None = None
    linked_ids: tuple[str, ...] | None = None
    active: bool | None = None


@router.patch("/directory/{organisation_id}", dependencies=[AdminOnly])
async def edit_organisation(
    state: ContainerDep, principal: PrincipalDep, organisation_id: str, body: OrganisationPatch
) -> dict:
    store = _store(state)
    current = next((o for o in store.organisations() if o.id == organisation_id), None)
    if current is None:
        raise HTTPException(404, "unknown organisation")
    changes = body.model_dump(exclude_unset=True)
    updated = Organisation.model_validate({**current.model_dump(), **changes})
    _check_links(state, updated)
    store.save_organisation(updated)
    ledger_change(state, principal, "organisation", organisation_id, changes)
    return updated.model_dump(mode="json")


# ---------------------------------------------------------------- roles

ROLE_BLURB: dict[Role, str] = {
    Role.ADMIN: "Runs the platform: directory, accounts, rules, everything below.",
    Role.DESK: "Registers families, enters records, confirms and releases reports.",
    Role.NAVIGATOR: "Looks after families day to day and books vendors.",
    Role.DOCTOR: "Approves re-plans that touch treatment timing; may see the medical background.",
    Role.CAREGIVER: "A family member: sees only their own family's journey.",
    Role.PATIENT: "The patient: sees only their own journey.",
}


def _routes(holder):
    """Every route, looking inside the routers an app has included."""
    for route in getattr(holder, "routes", ()):
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _routes(inner)
        else:
            yield route


@router.get("/admin/roles", dependencies=[AdminOnly])
async def roles(request: Request, state: ContainerDep) -> list[dict]:
    """Each role, what it is for and how many routes it may call, from the live access rules."""
    allowed: dict[Role, set[str]] = {r: set() for r in Role}
    for route in _routes(request.app):
        rules = [
            getattr(dep.dependency, "allowed", None) for dep in getattr(route, "dependencies", ())
        ]
        rules = [r for r in rules if r]
        if not rules or not getattr(route, "methods", None):
            continue
        method = sorted(route.methods - {"HEAD", "OPTIONS"})[0]
        for role in rules[0]:
            allowed[role].add(f"{method} {route.path}")
    users = state.identity.list_users() if state.identity is not None else []
    return [
        {
            "role": role.value,
            "blurb": ROLE_BLURB[role],
            "routes": len(allowed[role]),
            "accounts": sum(1 for u in users if u["role"] == role.value),
        }
        for role in Role
    ]
