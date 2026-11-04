"""Entering and importing a hospital's records.

Open only in the real world. In the demo the cohort is generated and a reset
rebuilds it, so anything entered would silently vanish; refusing is kinder.

Every write goes through `LiveWorld`, which writes it through to the store, and
then the family is re-planned at once: the point of entering a record is that the
answer changes, not that a row exists.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ..domain.enums import (
    REPORT_STEPS,
    Channel,
    FamilyMemberRole,
    Language,
    ResourceKind,
    StepKind,
    StepStatus,
)
from ..domain.models import CareStep, FamilyMember, Patient, Resource
from ..domain.pathway import DEFAULT_PATHWAY_ID, PATHWAYS
from ..ingest.records_import import (
    ImportBatch,
    csv_template,
    new_step_id,
    parse_csv,
    parse_fhir_bundle,
    step_problem,
)
from .access import AdminOnly, Desk, DeskWork, PrincipalDep
from .deps import ContainerDep

#: Deliberately plain: one @, something either side, a dot in the domain.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

router = APIRouter()


def _real_only(state: ContainerDep) -> None:
    if not state.world.real:
        raise HTTPException(
            409,
            "records can be entered only in the real world (SAATHI_WORLD=real); "
            "the demo's cohort is generated and a reset would discard them",
        )


# ---------------------------------------------------------------- patients


class FamilyMemberIn(BaseModel):
    name: str = Field(min_length=1)
    role: FamilyMemberRole = FamilyMemberRole.CAREGIVER_PRIMARY
    phone: str = Field(min_length=5)
    preferred_channel: Channel = Channel.WHATSAPP
    language: Language


class PatientIn(BaseModel):
    id: str | None = Field(default=None, description="Generated when omitted.")
    name: str = ""
    abha_number: str | None = None
    home_district: str = Field(min_length=1)
    home_distance_km: float = Field(ge=0)
    language: Language
    caregiver_phone: str = Field(min_length=5)
    #: Optional. A family with an email address can sign in with a code sent to it.
    caregiver_email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)
    hospital_id: str = Field(min_length=1)
    #: The care pathway this family is on (see `GET /pathways`).
    pathway_id: str = DEFAULT_PATHWAY_ID
    #: The visit this family is planned towards. Omitted means the pathway's own
    #: terminal visit (the review consult, for oncology).
    plan_target: StepKind | None = None
    family_members: list[FamilyMemberIn] = []


class PatientPatch(BaseModel):
    name: str | None = None
    abha_number: str | None = None
    home_district: str | None = None
    home_distance_km: float | None = Field(default=None, ge=0)
    language: Language | None = None
    caregiver_phone: str | None = None
    caregiver_email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)
    hospital_id: str | None = None
    pathway_id: str | None = None
    plan_target: StepKind | None = None


def _member(patient_id: str, body: FamilyMemberIn) -> FamilyMember:
    return FamilyMember(
        id=f"{patient_id}-m{uuid.uuid4().hex[:6]}",
        patient_id=patient_id,
        role=body.role,
        name=body.name,
        phone=body.phone,
        preferred_channel=body.preferred_channel,
        language=body.language,
    )


def _known_pathway(pathway_id: str) -> None:
    if pathway_id not in PATHWAYS:
        raise HTTPException(422, f"unknown pathway {pathway_id!r}; see GET /pathways")


@router.get("/pathways")
async def list_pathways() -> list[dict]:
    """The care pathways a family can be put on, and the steps each is made of."""
    return [
        {
            "id": p.id,
            "name": p.name,
            "default_target": p.default_target.value,
            "steps": sorted(k.value for k in p.kinds),
        }
        for p in PATHWAYS.values()
    ]


@router.post("/patients", status_code=201, dependencies=[DeskWork])
async def register_patient(state: ContainerDep, body: PatientIn) -> dict:
    _real_only(state)
    _known_pathway(body.pathway_id)
    patient_id = body.id or f"P-{uuid.uuid4().hex[:8].upper()}"
    patient = Patient(
        id=patient_id,
        name=body.name,
        abha_number=body.abha_number,
        home_district=body.home_district,
        home_distance_km=body.home_distance_km,
        language=body.language,
        caregiver_phone=body.caregiver_phone,
        caregiver_email=body.caregiver_email.lower() if body.caregiver_email else None,
        hospital_id=body.hospital_id,
        pathway_id=body.pathway_id,
        family_members=tuple(_member(patient_id, m) for m in body.family_members),
    )
    try:
        state.world.add_patient(patient, body.plan_target)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    await state.runner.plan_patient(patient_id, allow_render=True)
    return patient.model_dump(mode="json")


@router.patch("/patients/{patient_id}", dependencies=[DeskWork])
async def edit_patient(state: ContainerDep, patient_id: str, body: PatientPatch) -> dict:
    _real_only(state)
    if body.pathway_id is not None:
        _known_pathway(body.pathway_id)
    changes = body.model_dump(exclude_unset=True, exclude={"plan_target"})
    if changes.get("caregiver_email"):
        changes["caregiver_email"] = changes["caregiver_email"].lower()
    try:
        patient = state.world.update_patient(patient_id, **changes) if changes else (
            state.world.patient(patient_id)
        )
        if patient is None:
            raise LookupError(patient_id)
        if body.plan_target is not None:
            state.world.set_plan_target(patient_id, body.plan_target)
    except LookupError as exc:
        raise HTTPException(404, "unknown patient") from exc
    await state.runner.plan_patient(patient_id, allow_render=True)
    return patient.model_dump(mode="json")


@router.post("/patients/{patient_id}/family", status_code=201, dependencies=[DeskWork])
async def add_family_member(state: ContainerDep, patient_id: str, body: FamilyMemberIn) -> dict:
    _real_only(state)
    member = _member(patient_id, body)
    try:
        patient = state.world.add_family_member(patient_id, member)
    except LookupError as exc:
        raise HTTPException(404, "unknown patient") from exc
    return patient.model_dump(mode="json")


# ---------------------------------------------------------------- steps


class StepIn(BaseModel):
    id: str | None = None
    kind: StepKind
    status: StepStatus
    scheduled_for: date | None = None
    completed_on: date | None = Field(
        default=None, description="For a report: the day the sample was taken."
    )
    result_available_on: date | None = None
    queue: str | None = Field(
        default=None, description="The lab or department queue, e.g. pathology_report."
    )
    resource_id: str | None = None


class StepPatch(BaseModel):
    status: StepStatus | None = None
    scheduled_for: date | None = None
    completed_on: date | None = None
    queue: str | None = None
    resource_id: str | None = None


def _forecast(state: ContainerDep, step: CareStep) -> dict | None:
    """Whether the system can say when this report will land, said at entry."""
    if step.kind not in REPORT_STEPS or step.status is not StepStatus.PENDING_RESULT:
        return None
    predictor = state.planner.predictor
    n = predictor.n_calibration(step.queue or "")
    _, _, calibrated, _ = predictor.interval_days(step.queue or "")
    return {
        "queue": step.queue,
        "calibrated": calibrated,
        "observations": n,
        "note": (
            None
            if calibrated
            else f"no reliable forecast for {step.queue} yet ({n} past reports); "
            "the plan will say so rather than promise a date"
        ),
    }


@router.post("/patients/{patient_id}/steps", status_code=201, dependencies=[DeskWork])
async def add_step(state: ContainerDep, patient_id: str, body: StepIn) -> dict:
    _real_only(state)
    step = CareStep(
        id=body.id or new_step_id(patient_id, body.kind),
        patient_id=patient_id,
        kind=body.kind,
        status=body.status,
        scheduled_for=body.scheduled_for,
        completed_on=body.completed_on,
        result_available_on=body.result_available_on,
        queue=body.queue,
        resource_id=body.resource_id,
    )
    problem = step_problem(step)
    if problem:
        raise HTTPException(422, problem)
    try:
        state.world.add_step(step)
    except LookupError as exc:
        raise HTTPException(404, "unknown patient") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    await state.runner.plan_patient(patient_id, allow_render=True)
    return {"step": step.model_dump(mode="json"), "forecast": _forecast(state, step)}


@router.patch("/steps/{step_id}", dependencies=[DeskWork])
async def edit_step(state: ContainerDep, step_id: str, body: StepPatch) -> dict:
    _real_only(state)
    existing = state.world.step(step_id)
    if existing is None:
        raise HTTPException(404, "unknown step")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("status") is StepStatus.RESULT_AVAILABLE:
        raise HTTPException(
            422, "a report is released with POST /steps/{id}/release, so it is recorded"
        )
    problem = step_problem(existing.model_copy(update=changes))
    if problem:
        raise HTTPException(422, problem)
    step = state.world.update_step(step_id, **changes)
    await state.runner.plan_patient(step.patient_id, allow_render=True)
    return {"step": step.model_dump(mode="json"), "forecast": _forecast(state, step)}


class ReleaseIn(BaseModel):
    by: str = Field(default="desk staff", min_length=1)
    note: str = ""


@router.post("/steps/{step_id}/release", dependencies=[Desk])
async def release_step(
    state: ContainerDep,
    principal: PrincipalDep,
    step_id: str,
    body: Annotated[ReleaseIn | None, Body()] = None,
) -> dict:
    """A person says this report is ready. It is recorded, and the family re-planned."""
    _real_only(state)
    try:
        body = body or ReleaseIn()
        by = principal.name if principal else body.by
        step = await state.runner.release_step(step_id, by=by, note=body.note)
    except LookupError as exc:
        raise HTTPException(404, "unknown step") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"step": step.model_dump(mode="json")}


# ---------------------------------------------------------------- resources


class ResourceIn(BaseModel):
    id: str = Field(min_length=1)
    kind: ResourceKind
    display_name: str = Field(min_length=1)
    hospital_id: str = Field(min_length=1)
    department: str = Field(min_length=1)


@router.post("/resources", status_code=201, dependencies=[AdminOnly])
async def register_resource(state: ContainerDep, body: ResourceIn) -> dict:
    _real_only(state)
    resource = Resource(**body.model_dump())
    state.world.register_resource(resource)
    return resource.model_dump(mode="json")


# ---------------------------------------------------------------- import


def _known(state: ContainerDep) -> tuple[set[str], set[str]]:
    return (
        {p.id for p in state.world.patients()},
        set(state.world.index),
    )


async def _apply(state: ContainerDep, batch: ImportBatch) -> dict:
    """Write a clean batch. Existing records are updated in place."""
    world, runner = state.world, state.runner
    touched: set[str] = set()
    for patient, target in batch.patients:
        if world.patient(patient.id) is None:
            world.add_patient(patient, target)
        else:
            world.update_patient(
                patient.id,
                **{k: getattr(patient, k) for k in (
                    "name", "abha_number", "home_district", "home_distance_km",
                    "language", "caregiver_phone", "hospital_id",
                )},
            )  # fmt: skip
            if target is not None:
                world.set_plan_target(patient.id, target)
        touched.add(patient.id)
    for member in batch.family:
        current = world.patient(member.patient_id)
        if current is not None and all(m.id != member.id for m in current.family_members):
            world.add_family_member(member.patient_id, member)
        touched.add(member.patient_id)
    released = 0
    for step in batch.steps:
        touched.add(step.patient_id)
        existing = world.step(step.id)
        arriving = step.status is StepStatus.RESULT_AVAILABLE and step.kind in REPORT_STEPS
        if existing is None:
            if arriving:
                # Enter it pending, then release it, so the ledger records the
                # release exactly as it does for a person confirming one.
                pending = step.model_copy(
                    update={"status": StepStatus.PENDING_RESULT, "result_available_on": None}
                )
                if pending.completed_on is not None and pending.queue:
                    world.add_step(pending)
                    await runner.release_step(step.id, by="import")
                    released += 1
                    continue
            world.add_step(step)
        elif arriving and existing.status is not StepStatus.RESULT_AVAILABLE:
            await runner.release_step(step.id, by="import")
            released += 1
        else:
            world.update_step(
                step.id,
                status=step.status,
                scheduled_for=step.scheduled_for,
                completed_on=step.completed_on,
                queue=step.queue,
                resource_id=step.resource_id,
            )
    for patient_id in sorted(touched):
        await runner.plan_patient(patient_id, allow_render=True)
    return {"applied": True, "released": released, "replanned": len(touched)}


def _report(batch: ImportBatch, *, committed: dict | None) -> dict:
    return {
        "counts": batch.counts(),
        "errors": [e.to_json() for e in batch.errors],
        "skipped": [e.to_json() for e in batch.skipped],
        "committed": committed,
    }


@router.get("/import/template.csv", response_class=PlainTextResponse)
async def import_template() -> str:
    return csv_template()


@router.post("/import/csv", dependencies=[Desk])
async def import_csv(request: Request, state: ContainerDep, commit: bool = False) -> dict:
    """The CSV template as the request body (`text/csv`).

    Without `commit=true` this is a dry run: it says what would be written and
    what is wrong. With it, the batch is written only if nothing is wrong.
    """
    _real_only(state)
    text = (await request.body()).decode("utf-8", errors="replace")
    patients, steps = _known(state)
    batch = parse_csv(text, known_patients=patients, known_steps=steps)
    if commit and not batch.clean:
        raise HTTPException(422, _report(batch, committed=None))
    return _report(batch, committed=await _apply(state, batch) if commit else None)


@router.post("/import/fhir", dependencies=[Desk])
async def import_fhir(
    state: ContainerDep,
    bundle: Annotated[dict, Body()],
    hospital_id: str,
    commit: bool = False,
    default_distance_km: float | None = None,
    default_language: Language = Language.HINDI,
) -> dict:
    """A FHIR R4 Bundle of Patient, RelatedPerson, Appointment, DiagnosticReport.

    Report content (`conclusion`, `presentedForm`, `result`) is dropped before
    anything is stored: only status and dates are kept.
    """
    _real_only(state)
    patients, _ = _known(state)
    batch = parse_fhir_bundle(
        bundle,
        hospital_id=hospital_id,
        default_distance_km=default_distance_km,
        default_language=default_language,
        known_patients=patients,
    )
    if commit and not batch.clean:
        raise HTTPException(422, _report(batch, committed=None))
    return _report(batch, committed=await _apply(state, batch) if commit else None)
