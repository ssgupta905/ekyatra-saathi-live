"""Taking a family on: what they tell us, what the hospital adds, and when they are ready.

Stage 1 is gathered from the family (who they are, background, documents, a
doctor's note of their medical background, their agreement to share). Stage 2 is
added by the hospital for each admission. A family is activated only when every
stage is done. Every change writes a ledger row naming who made it and which
section, never what it says.
"""

from __future__ import annotations

import base64
import binascii
import uuid

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ValidationError

from ..domain.enums import Role, SourceSystem
from ..domain.pathway import PATHWAYS
from ..domain.profile import (
    DOCUMENT_LABELS,
    MAX_DOCUMENT_BYTES,
    RESTRICTED,
    SECTIONS,
    STAGES,
    Admission,
    AdmissionForm,
    DocumentKind,
    DocumentRecord,
    DocumentUpload,
    mask_number,
    stage_states,
)
from ..ports.identity import Principal
from .access import AnyStaff, DeskWork, PrincipalDep
from .deps import ContainerDep
from .registry import who

router = APIRouter(tags=["onboarding"])


def _store(state: ContainerDep):
    if state.onboarding is None:
        raise HTTPException(503, "onboarding is not configured")
    return state.onboarding


def _patient(state: ContainerDep, patient_id: str):
    patient = state.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")
    return patient


def _may_use(principal: Principal | None, section: str) -> bool:
    allowed = RESTRICTED.get(section)
    return not allowed or principal is None or principal.role.value in allowed


def _ensure_may_write(principal: Principal | None, section: str) -> None:
    """Desk, navigators and administrators fill the family's sections; a doctor does the medical."""
    if principal is None or section in RESTRICTED:
        return _ensure_may_use(principal, section)
    if principal.role not in (Role.DESK, Role.NAVIGATOR, Role.ADMIN):
        raise HTTPException(403, f"{principal.role.value} may not edit the {section} section")


def _ensure_may_use(principal: Principal | None, section: str) -> None:
    """The medical section: doctors and administrators only. Open when login is off."""
    if not _may_use(principal, section):
        raise HTTPException(403, f"{principal.role.value} may not see the {section} section")


def _audit(state: ContainerDep, principal: Principal | None, patient_id: str, claim: str) -> None:
    """Record that something changed and who changed it, never what it says."""
    state.ledger.record(
        patient_id=patient_id,
        source=SourceSystem.NAVIGATOR,
        source_record_id=f"onboarding/{patient_id}/{uuid.uuid4().hex[:8]}",
        claim=claim,
        metadata={"by": who(principal)},
    )


# ---------------------------------------------------------------- the forms


@router.get("/forms/{name}", dependencies=[AnyStaff])
async def form(name: str, principal: PrincipalDep) -> dict:
    """A form as JSON Schema: the control centre draws it, so a new field needs no screen change."""
    if name == "admission":
        return AdmissionForm.model_json_schema()
    if name not in SECTIONS:
        raise HTTPException(404, "no such form")
    _ensure_may_use(principal, name)
    return SECTIONS[name].model_json_schema()


@router.get("/forms", dependencies=[AnyStaff])
async def forms(principal: PrincipalDep) -> dict:
    return {
        "sections": [n for n in SECTIONS if _may_use(principal, n)],
        "documents": [{"kind": k.value, "label": DOCUMENT_LABELS[k]} for k in DocumentKind],
        "pathways": [{"id": p.id, "name": p.name} for p in PATHWAYS.values()],
    }


# ---------------------------------------------------------------- the stages


def _consented(state: ContainerDep, patient) -> bool:
    if state.consent is None or not patient.abha_number:
        return False
    return any(
        g.purpose.value == "care_coordination"
        for g in state.consent.active_grants(patient.abha_number)
    )


def _status(state: ContainerDep, patient_id: str) -> dict:
    patient = _patient(state, patient_id)
    store = _store(state)
    stages = stage_states(
        saved=store.saved_sections(patient_id),
        documents=store.documents(patient_id),
        admissions=store.admissions(patient_id),
        consented=_consented(state, patient),
        care_steps=len(state.world.steps_for(patient_id)),
    )
    active = store.activation(patient_id)
    return {
        "patient_id": patient_id,
        "name": patient.name or patient_id,
        "stages": [s.model_dump() for s in stages],
        "done": sum(1 for s in stages if s.done),
        "total": len(STAGES),
        "ready": all(s.done for s in stages),
        "activated": {"by": active[0], "at": active[1]} if active else None,
    }


@router.get("/onboarding", dependencies=[AnyStaff])
async def everyone(state: ContainerDep) -> list[dict]:
    """Every family and how far along they are, least finished first."""
    rows = [_status(state, p.id) for p in state.world.patients()]
    rows.sort(key=lambda r: (r["activated"] is not None, r["done"]))
    return [
        {k: r[k] for k in ("patient_id", "name", "done", "total", "ready", "activated")}
        for r in rows
    ]


@router.get("/patients/{patient_id}/onboarding", dependencies=[AnyStaff])
async def status(state: ContainerDep, patient_id: str) -> dict:
    return _status(state, patient_id)


@router.post("/patients/{patient_id}/activate", dependencies=[DeskWork])
async def activate(state: ContainerDep, principal: PrincipalDep, patient_id: str) -> dict:
    current = _status(state, patient_id)
    if not current["ready"]:
        missing = [m for s in current["stages"] for m in s["missing"]]
        raise HTTPException(409, {"message": "onboarding is not finished", "missing": missing})
    _store(state).activate(patient_id, who(principal))
    _audit(state, principal, patient_id, "family activated")
    return _status(state, patient_id)


# ---------------------------------------------------------------- sections


@router.get("/patients/{patient_id}/profile/{section}", dependencies=[AnyStaff])
async def get_section(
    state: ContainerDep, principal: PrincipalDep, patient_id: str, section: str
) -> dict:
    _patient(state, patient_id)
    if section not in SECTIONS:
        raise HTTPException(404, "no such section")
    _ensure_may_use(principal, section)
    saved = _store(state).section(patient_id, section)
    if saved is None:
        return {"saved": False, "data": {}}
    data, by, at = saved
    return {"saved": True, "data": data, "by": by, "at": at}


class _Raw(BaseModel):
    model_config = {"extra": "allow"}


@router.put("/patients/{patient_id}/profile/{section}", dependencies=[AnyStaff])
async def put_section(
    state: ContainerDep, principal: PrincipalDep, patient_id: str, section: str, body: _Raw
) -> dict:
    patient = _patient(state, patient_id)
    if section not in SECTIONS:
        raise HTTPException(404, "no such section")
    _ensure_may_write(principal, section)
    try:
        parsed = SECTIONS[section].model_validate(body.model_dump())
    except ValidationError as exc:
        problems = [
            {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
            for e in exc.errors()
        ]
        raise HTTPException(422, problems) from exc
    _store(state).save_section(patient_id, section, parsed.model_dump(mode="json"), who(principal))
    _audit(state, principal, patient_id, f"{section} details saved")
    if section == "identity":
        # Contact details are what sign-in and messages use, so they live on the family record too.
        state.world.update_patient(
            patient_id,
            name=parsed.patient_name,
            caregiver_phone=parsed.caregiver_phone,
            caregiver_email=parsed.caregiver_email.lower() if parsed.caregiver_email else None,
            language=parsed.language,
            home_district=parsed.district,
        )
    return {"saved": True, "patient_id": patient.id, "section": section}


# ---------------------------------------------------------------- documents


@router.get("/patients/{patient_id}/documents", dependencies=[AnyStaff])
async def documents(state: ContainerDep, patient_id: str) -> list[dict]:
    _patient(state, patient_id)
    return [d.model_dump(mode="json") for d in _store(state).documents(patient_id)]


@router.post("/patients/{patient_id}/documents", status_code=201, dependencies=[DeskWork])
async def upload_document(
    state: ContainerDep, principal: PrincipalDep, patient_id: str, body: DocumentUpload
) -> dict:
    _patient(state, patient_id)
    try:
        content = base64.b64decode(body.data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(422, "the file is not valid base64") from exc
    if len(content) > MAX_DOCUMENT_BYTES:
        raise HTTPException(413, "the file is larger than 5 MB")
    record = DocumentRecord(
        id=f"doc-{uuid.uuid4().hex[:12]}",
        patient_id=patient_id,
        kind=body.kind,
        number_masked=mask_number(body.number),
        issuer=body.issuer,
        filename=body.filename,
        content_type=body.content_type,
        size=len(content),
        uploaded_by=who(principal),
    )
    _store(state).save_document(record, content)
    _audit(state, principal, patient_id, f"{body.kind.value} document uploaded")
    return record.model_dump(mode="json")


@router.get("/patients/{patient_id}/documents/{document_id}", dependencies=[DeskWork])
async def download_document(state: ContainerDep, patient_id: str, document_id: str) -> Response:
    found = _store(state).document(document_id)
    if found is None or found[0].patient_id != patient_id:
        raise HTTPException(404, "no such document")
    record, content = found
    return Response(
        content,
        media_type=record.content_type,
        headers={"content-disposition": f'inline; filename="{record.filename}"'},
    )


@router.post("/patients/{patient_id}/documents/{document_id}/verify", dependencies=[DeskWork])
async def verify_document(
    state: ContainerDep, principal: PrincipalDep, patient_id: str, document_id: str
) -> dict:
    found = _store(state).document(document_id)
    if found is None or found[0].patient_id != patient_id:
        raise HTTPException(404, "no such document")
    record = _store(state).verify_document(document_id, who(principal))
    _audit(state, principal, patient_id, f"{found[0].kind.value} document checked")
    return record.model_dump(mode="json")


# ---------------------------------------------------------------- admissions


def _check_admission(state: ContainerDep, form: AdmissionForm) -> None:
    registry = state.registry
    if registry is None or not any(h.id == form.hospital_id for h in registry.hospitals()):
        raise HTTPException(422, f"no hospital {form.hospital_id} in the registry")
    if form.pathway_id not in PATHWAYS:
        raise HTTPException(422, f"unknown pathway {form.pathway_id}")
    if form.clinician_id and not any(c.id == form.clinician_id for c in registry.clinicians()):
        raise HTTPException(422, f"no clinician {form.clinician_id} in the registry")


@router.get("/patients/{patient_id}/admissions", dependencies=[AnyStaff])
async def admissions(state: ContainerDep, patient_id: str) -> list[dict]:
    _patient(state, patient_id)
    return [a.model_dump(mode="json") for a in _store(state).admissions(patient_id)]


@router.post("/patients/{patient_id}/admissions", status_code=201, dependencies=[DeskWork])
async def add_admission(
    state: ContainerDep, principal: PrincipalDep, patient_id: str, body: AdmissionForm
) -> dict:
    patient = _patient(state, patient_id)
    _check_admission(state, body)
    admission = Admission(
        id=f"adm-{uuid.uuid4().hex[:10]}", patient_id=patient_id, **body.model_dump()
    )
    _store(state).save_admission(admission)
    if patient.pathway_id != body.pathway_id:
        state.world.update_patient(patient_id, pathway_id=body.pathway_id)
    _audit(state, principal, patient_id, f"admission recorded at {body.hospital_id}")
    return admission.model_dump(mode="json")


@router.patch("/patients/{patient_id}/admissions/{admission_id}", dependencies=[DeskWork])
async def edit_admission(
    state: ContainerDep,
    principal: PrincipalDep,
    patient_id: str,
    admission_id: str,
    body: AdmissionForm,
) -> dict:
    _patient(state, patient_id)
    current = next((a for a in _store(state).admissions(patient_id) if a.id == admission_id), None)
    if current is None:
        raise HTTPException(404, "no such admission")
    _check_admission(state, body)
    updated = Admission(id=current.id, patient_id=patient_id, **body.model_dump())
    _store(state).save_admission(updated)
    _audit(state, principal, patient_id, f"admission {admission_id} changed")
    return updated.model_dump(mode="json")

