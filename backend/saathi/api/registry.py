"""The hospital network's registries, and staff accounts.

Read by every staff role; changed by administrators. Every change writes a ledger
row naming who made it, so the audit log answers "who moved this centre" as
readily as "who released this report".
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..domain.enums import ResourceKind, Role, SourceSystem
from ..domain.models import Resource
from ..domain.registry import Clinician, Hospital, NetworkCentre
from ..ports.identity import Principal
from .access import AdminOnly, AnyStaff, PrincipalDep
from .deps import ContainerDep

router = APIRouter()

#: The ledger's patient column, for facts about the hospital rather than a family.
REGISTRY = "registry"


def who(principal: Principal | None) -> str:
    return principal.name if principal else "demo (no sign-in)"


def ledger(state: ContainerDep, principal: Principal | None, record: str, claim: str) -> None:
    state.ledger.record(
        patient_id=REGISTRY,
        source=SourceSystem.NAVIGATOR,
        source_record_id=record,
        claim=claim,
        metadata={"by": who(principal)},
    )


def ledger_change(
    state: ContainerDep, principal: Principal | None, kind: str, record_id: str, changes: dict
) -> None:
    fields = ", ".join(sorted(changes)) or "nothing"
    ledger(state, principal, f"{kind}/{record_id}", f"{kind} {record_id} changed: {fields}")


def _store(state: ContainerDep):
    if state.registry is None:
        raise HTTPException(503, "no registry is configured")
    return state.registry


# ---------------------------------------------------------------- hospitals


@router.get("/registry/hospitals", dependencies=[AnyStaff])
async def hospitals(state: ContainerDep) -> list[dict]:
    return [h.model_dump(mode="json") for h in _store(state).hospitals()]


@router.post("/registry/hospitals", status_code=201, dependencies=[AdminOnly])
async def add_hospital(state: ContainerDep, principal: PrincipalDep, body: Hospital) -> dict:
    store = _store(state)
    if any(h.id == body.id for h in store.hospitals()):
        raise HTTPException(409, f"hospital {body.id} already exists")
    store.save_hospital(body)
    ledger(state, principal, f"hospital/{body.id}", f"hospital {body.id} added: {body.name}")
    return body.model_dump(mode="json")


class HospitalPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    place: str | None = Field(default=None, min_length=1)
    timezone: str | None = None
    departments: tuple[str, ...] | None = None
    active: bool | None = None


@router.patch("/registry/hospitals/{hospital_id}", dependencies=[AdminOnly])
async def edit_hospital(
    state: ContainerDep, principal: PrincipalDep, hospital_id: str, body: HospitalPatch
) -> dict:
    store = _store(state)
    current = next((h for h in store.hospitals() if h.id == hospital_id), None)
    if current is None:
        raise HTTPException(404, "unknown hospital")
    changes = body.model_dump(exclude_unset=True)
    updated = Hospital.model_validate({**current.model_dump(), **changes})
    store.save_hospital(updated)
    ledger_change(state, principal, "hospital", hospital_id, changes)
    return updated.model_dump(mode="json")


# ---------------------------------------------------------------- centres


@router.get("/registry/centres", dependencies=[AnyStaff])
async def centres(state: ContainerDep) -> list[dict]:
    return [c.model_dump(mode="json") for c in _store(state).centres()]


def _known_hospital(state: ContainerDep, hospital_id: str) -> None:
    if not any(h.id == hospital_id for h in _store(state).hospitals()):
        raise HTTPException(422, f"no hospital {hospital_id} in the registry")


@router.post("/registry/centres", status_code=201, dependencies=[AdminOnly])
async def add_centre(state: ContainerDep, principal: PrincipalDep, body: NetworkCentre) -> dict:
    store = _store(state)
    _known_hospital(state, body.hospital_id)
    if any(c.id == body.id for c in store.centres()):
        raise HTTPException(409, f"centre {body.id} already exists")
    store.save_centre(body)
    ledger(state, principal, f"centre/{body.id}", f"centre {body.id} added: {body.name}")
    return body.model_dump(mode="json")


class CentrePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    place: str | None = Field(default=None, min_length=1)
    kind: str | None = Field(default=None, pattern="^(hub|day_care)$")
    handles: tuple[str, ...] | None = None
    active: bool | None = None


@router.patch("/registry/centres/{centre_id}", dependencies=[AdminOnly])
async def edit_centre(
    state: ContainerDep, principal: PrincipalDep, centre_id: str, body: CentrePatch
) -> dict:
    store = _store(state)
    current = next((c for c in store.centres() if c.id == centre_id), None)
    if current is None:
        raise HTTPException(404, "unknown centre")
    changes = body.model_dump(exclude_unset=True)
    updated = NetworkCentre.model_validate({**current.model_dump(), **changes})
    store.save_centre(updated)
    ledger_change(state, principal, "centre", centre_id, changes)
    return updated.model_dump(mode="json")


# ---------------------------------------------------------------- clinicians


@router.get("/registry/clinicians", dependencies=[AnyStaff])
async def clinicians(state: ContainerDep) -> list[dict]:
    return [c.model_dump(mode="json") for c in _store(state).clinicians()]


@router.post("/registry/clinicians", status_code=201, dependencies=[AdminOnly])
async def add_clinician(state: ContainerDep, principal: PrincipalDep, body: Clinician) -> dict:
    store = _store(state)
    _known_hospital(state, body.hospital_id)
    if any(c.id == body.id for c in store.clinicians()):
        raise HTTPException(409, f"clinician {body.id} already exists")
    store.save_clinician(body)
    ledger(state, principal, f"clinician/{body.id}", f"clinician {body.id} added: {body.name}")
    return body.model_dump(mode="json")


class ClinicianPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    specialty: str | None = None
    hospital_id: str | None = None
    department: str | None = None
    username: str | None = None
    active: bool | None = None


@router.patch("/registry/clinicians/{clinician_id}", dependencies=[AdminOnly])
async def edit_clinician(
    state: ContainerDep, principal: PrincipalDep, clinician_id: str, body: ClinicianPatch
) -> dict:
    store = _store(state)
    current = next((c for c in store.clinicians() if c.id == clinician_id), None)
    if current is None:
        raise HTTPException(404, "unknown clinician")
    changes = body.model_dump(exclude_unset=True)
    if "hospital_id" in changes:
        _known_hospital(state, changes["hospital_id"])
    updated = Clinician.model_validate({**current.model_dump(), **changes})
    store.save_clinician(updated)
    ledger_change(state, principal, "clinician", clinician_id, changes)
    return updated.model_dump(mode="json")


# ---------------------------------------------------------------- resources


@router.get("/resources", dependencies=[AnyStaff])
async def resources(state: ContainerDep) -> list[dict]:
    """Machines, staff roles and supplies a desk can report unavailable."""
    return [r.model_dump(mode="json") for r in state.world.resources.values()]


class ResourcePatch(BaseModel):
    kind: ResourceKind | None = None
    display_name: str | None = Field(default=None, min_length=1)
    hospital_id: str | None = None
    department: str | None = None


@router.patch("/resources/{resource_id}", dependencies=[AdminOnly])
async def edit_resource(
    state: ContainerDep, principal: PrincipalDep, resource_id: str, body: ResourcePatch
) -> dict:
    current = state.world.resources.get(resource_id)
    if current is None:
        raise HTTPException(404, "unknown resource")
    changes = body.model_dump(exclude_unset=True)
    updated = Resource.model_validate({**current.model_dump(), **changes})
    state.world.register_resource(updated)
    ledger_change(state, principal, "resource", resource_id, changes)
    return updated.model_dump(mode="json")


# ---------------------------------------------------------------- staff accounts


def _accounts(state: ContainerDep):
    identity = state.identity
    if identity is None or not hasattr(identity, "list_users"):
        raise HTTPException(
            409, "staff accounts exist only where login is on (the real world)"
        )
    return identity


@router.get("/admin/users", dependencies=[AdminOnly])
async def users(state: ContainerDep) -> list[dict]:
    return _accounts(state).list_users()


class UserIn(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    name: str = Field(min_length=1, max_length=160)
    role: Role
    password: str = Field(min_length=8, max_length=256)


@router.post("/admin/users", status_code=201, dependencies=[AdminOnly])
async def add_user(state: ContainerDep, principal: PrincipalDep, body: UserIn) -> dict:
    identity = _accounts(state)
    if any(u["username"] == body.username.lower() for u in identity.list_users()):
        raise HTTPException(409, f"{body.username} already exists")
    try:
        identity.add_user(body.username, body.name, body.role, body.password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    ledger(state, principal, f"user/{body.username.lower()}",
           f"staff account {body.username.lower()} created as {body.role.value}")  # fmt: skip
    return next(u for u in identity.list_users() if u["username"] == body.username.lower())


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    role: Role | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


@router.patch("/admin/users/{username}", dependencies=[AdminOnly])
async def edit_user(
    state: ContainerDep, principal: PrincipalDep, username: str, body: UserPatch
) -> dict:
    if principal is not None and principal.id and body.active is False:
        me = next((u for u in _accounts(state).list_users() if u["id"] == principal.id), None)
        if me and me["username"] == username.lower():
            raise HTTPException(422, "you cannot deactivate your own account")
    try:
        updated = _accounts(state).update_user(username, **body.model_dump(exclude_unset=True))
    except LookupError as exc:
        raise HTTPException(404, "unknown account") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    changed = {
        ("password reset" if k == "password" else k): True
        for k in body.model_dump(exclude_unset=True)
    }
    ledger_change(state, principal, "user", username.lower(), changed)
    return updated
