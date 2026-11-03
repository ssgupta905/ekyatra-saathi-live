"""Consent: ask a family, record their answer, withdraw it, and check it at every read.

Everything is keyed by the family (`/patients/{patient_id}/consent/...`) rather
than by ABHA number, for the same reason the rest of the API is: a caregiver may
act only for their own family, and the path is where that is checked. The ABHA
number is read off the patient record; a family without one has nothing to
consent about and is told so.

Saathi is the requester here, never the consent manager. It asks, the patient
answers in their own language, and the source holds the record. These routes
move no clinical content: a `RecordPointer` says that a document exists and
where, and has no field that could say what it found.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..consent.registry import ConsentError
from ..domain.consent import (
    AccessOutcome,
    ConsentCapacity,
    ConsentPurpose,
    RecordPointer,
)
from ..domain.enums import Channel, Language, SourceSystem
from .access import DeskWork, FamilyOrStaff, PrincipalDep
from .deps import ContainerDep

router = APIRouter(prefix="/patients/{patient_id}/consent", tags=["consent"])


class RequestIn(BaseModel):
    purpose: ConsentPurpose
    requester_id: str = Field(min_length=1, max_length=64)
    requester_name: str = Field(min_length=1, max_length=120)
    categories: list[str] = Field(
        min_length=1, description="Never empty: 'everything' is not a purpose."
    )
    reason: str = Field(default="", max_length=300)
    from_date: date | None = None
    to_date: date | None = None
    notice_language: Language | None = Field(
        default=None, description="Defaults to the family's own language."
    )


class GrantIn(BaseModel):
    granted_by: str = Field(min_length=1, max_length=120)
    #: Stated, never inferred: whoever answered the phone is not thereby a nominee.
    capacity: ConsentCapacity
    channel: Channel
    days: int | None = Field(default=None, ge=1, le=365)


class RevokeIn(BaseModel):
    by: str = Field(min_length=1, max_length=120)
    reason: str = Field(default="", max_length=300)


class PointerIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    care_context_id: str
    test_name: str
    category: str
    performed_on: date
    source_name: str
    source_system: SourceSystem = SourceSystem.HOSPITAL_FEED
    source_reference: str
    in_health_locker: bool = False


class ResolveIn(BaseModel):
    requester_id: str = Field(min_length=1, max_length=64)
    purpose: ConsentPurpose


def _abha(state: ContainerDep, patient_id: str) -> str:
    patient = state.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")
    if not patient.abha_number:
        raise HTTPException(
            409, "this family has no ABHA number on record, so there is nothing to consent about"
        )
    return patient.abha_number


def _grant_json(grant) -> dict:
    return {
        "id": grant.id,
        "request_id": grant.request_id,
        "purpose": grant.purpose.value,
        "requester_id": grant.requester_id,
        "requester": grant.requester_name,
        "categories": list(grant.categories),
        "granted_by": grant.granted_by,
        "capacity": grant.capacity.value,
        "channel": grant.channel.value,
        "language": grant.notice_language.value,
        "granted_at": grant.granted_at.isoformat(),
        "expires_at": grant.expires_at.isoformat(),
        "active": grant.is_active(),
        "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None,
    }


def _attempt_json(attempt) -> dict:
    return {
        "id": attempt.id,
        "pointer_id": attempt.pointer_id,
        "requester_id": attempt.requester_id,
        "purpose": attempt.purpose.value,
        "outcome": attempt.outcome.value,
        "at": attempt.at.isoformat(),
        "grant_id": attempt.grant_id,
    }


@router.get("", dependencies=[FamilyOrStaff])
async def consent_snapshot(state: ContainerDep, patient_id: str) -> dict:
    """Grants, what is waiting to be answered, and how often a door was tried."""
    return state.consent.snapshot(_abha(state, patient_id))


@router.post("/requests", status_code=201, dependencies=[DeskWork])
async def request_consent(state: ContainerDep, patient_id: str, body: RequestIn) -> dict:
    abha = _abha(state, patient_id)
    patient = state.world.patient(patient_id)
    try:
        request = state.consent.request(
            abha_number=abha,
            purpose=body.purpose,
            requester_id=body.requester_id,
            requester_name=body.requester_name,
            categories=tuple(body.categories),
            reason=body.reason,
            from_date=body.from_date,
            to_date=body.to_date,
            notice_language=body.notice_language or patient.language,
        )
    except ConsentError as exc:
        raise HTTPException(422, str(exc)) from exc
    return request.model_dump(mode="json")


@router.post("/requests/{request_id}/grant", status_code=201, dependencies=[FamilyOrStaff])
async def grant_consent(
    state: ContainerDep, patient_id: str, request_id: str, body: GrantIn
) -> dict:
    abha = _abha(state, patient_id)
    request = state.consent.requests.get(request_id)
    if request is None or request.abha_number != abha:
        raise HTTPException(404, "no such consent request for this family")
    if any(g.request_id == request_id for g in state.consent.grants.values()):
        raise HTTPException(409, "this request has already been answered")
    return _grant_json(
        state.consent.grant(
            request_id,
            granted_by=body.granted_by,
            capacity=body.capacity,
            channel=body.channel,
            days=body.days,
        )
    )


@router.post("/grants/{grant_id}/revoke", dependencies=[FamilyOrStaff])
async def revoke_consent(
    state: ContainerDep, patient_id: str, grant_id: str, body: RevokeIn
) -> dict:
    """Stops future access. It undoes nothing a centre already lawfully received."""
    abha = _abha(state, patient_id)
    grant = state.consent.grants.get(grant_id)
    if grant is None or grant.abha_number != abha:
        raise HTTPException(404, "no such grant for this family")
    return _grant_json(state.consent.revoke(grant_id, by=body.by, reason=body.reason))


@router.get("/active", dependencies=[FamilyOrStaff])
async def active_consent(state: ContainerDep, patient_id: str) -> list[dict]:
    return [_grant_json(g) for g in state.consent.active_grants(_abha(state, patient_id))]


@router.get("/access-log", dependencies=[FamilyOrStaff])
async def access_log(state: ContainerDep, patient_id: str) -> list[dict]:
    """Every attempt to open a record, refusals included, newest first."""
    attempts = state.consent.access_log(_abha(state, patient_id))
    return [_attempt_json(a) for a in sorted(attempts, key=lambda a: a.at, reverse=True)]


@router.post("/records", status_code=201, dependencies=[DeskWork])
async def index_record(state: ContainerDep, patient_id: str, body: PointerIn) -> dict:
    """Note that a record exists and where. Its contents never come through here."""
    pointer = RecordPointer(abha_number=_abha(state, patient_id), **body.model_dump())
    existing = state.consent.pointers.get(pointer.id)
    if existing is not None and existing.abha_number != pointer.abha_number:
        raise HTTPException(409, "that record id belongs to another family")
    state.consent.add_pointer(pointer)
    return pointer.as_seen_by("admin")


@router.get("/records", dependencies=[FamilyOrStaff])
async def record_timeline(
    state: ContainerDep, patient_id: str, principal: PrincipalDep
) -> list[dict]:
    """The family's indexed records, redacted for whoever is looking.

    With login off there is nobody to redact for, so the redacted view is used:
    the safe reading of "unknown role" is the one a navigator gets.
    """
    role = principal.role.value if principal is not None else "navigator"
    return state.consent.timeline(_abha(state, patient_id), role=role)


@router.post("/records/{pointer_id}/resolve", dependencies=[DeskWork])
async def resolve_record(
    state: ContainerDep, patient_id: str, pointer_id: str, body: ResolveIn
) -> dict:
    """Check live consent and hand over the pointer, or refuse and say why.

    A refusal is logged exactly as a success is, and answers 403 with the reason:
    "withdrawn", "expired", "outside what was agreed" and "never asked" are
    different facts with different obligations.
    """
    abha = _abha(state, patient_id)
    pointer = state.consent.pointers.get(pointer_id)
    if pointer is None or pointer.abha_number != abha:
        raise HTTPException(404, "no such record for this family")
    outcome, resolved = state.consent.resolve(
        pointer_id, requester_id=body.requester_id, purpose=body.purpose
    )
    if outcome is not AccessOutcome.GRANTED:
        raise HTTPException(403, {"outcome": outcome.value, "pointer_id": pointer_id})
    return {"outcome": outcome.value, "pointer": resolved.as_seen_by("admin")}
