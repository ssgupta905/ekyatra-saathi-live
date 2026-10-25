"""Bringing a hospital's existing records in: a CSV template, or a FHIR bundle.

Both routes produce the same thing, an `ImportBatch`: what would be written and
what is wrong with the rest. Nothing here writes. The API shows the batch first
(a dry run) and applies it only if it is clean, so a typo on row 40 never leaves
39 families half-entered.

Both routes stop at the same line the rest of the project does: status, dates
and identifiers come in; a report's content does not. A FHIR `conclusion` is
dropped by `to_care_step` before it reaches this module, and the CSV has no
column that could hold one.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..domain.enums import (
    REPORT_STEPS,
    Channel,
    FamilyMemberRole,
    Language,
    StepKind,
    StepStatus,
)
from ..domain.models import CareStep, FamilyMember, Patient
from .abdm import to_care_step

#: The CSV template, one file with a `record_type` column. Order matters only to
#: a person reading it.
CSV_COLUMNS = (
    "record_type", "id", "patient_id", "name", "abha_number", "home_district",
    "home_distance_km", "language", "caregiver_phone", "hospital_id", "plan_target",
    "kind", "status", "scheduled_for", "completed_on", "result_available_on",
    "queue", "resource_id", "role", "phone", "channel",
)  # fmt: skip

DISTANCE_EXTENSION = "https://ekyatra.org/fhir/home-distance-km"


@dataclass
class ImportIssue:
    where: str
    message: str

    def to_json(self) -> dict:
        return {"where": self.where, "message": self.message}


@dataclass
class ImportBatch:
    patients: list[tuple[Patient, StepKind | None]] = field(default_factory=list)
    family: list[FamilyMember] = field(default_factory=list)
    steps: list[CareStep] = field(default_factory=list)
    errors: list[ImportIssue] = field(default_factory=list)
    #: Things readable but not usable (a FHIR resource we cannot classify).
    skipped: list[ImportIssue] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.errors

    def counts(self) -> dict[str, int]:
        return {
            "patients": len(self.patients),
            "family_members": len(self.family),
            "steps": len(self.steps),
            "errors": len(self.errors),
            "skipped": len(self.skipped),
        }


def step_problem(step: CareStep) -> str | None:
    """Why this step cannot be planned around, or None when it can.

    The planner answers UNCERTAIN for a report it cannot anchor, which is safe
    but looks like a bug to whoever entered it. Saying so at entry is kinder.
    """
    if step.kind in REPORT_STEPS and step.status is StepStatus.PENDING_RESULT:
        if not step.queue:
            return "a pending report needs a queue (for example pathology_report)"
        if step.completed_on is None:
            return "a pending report needs the date the sample was taken (completed_on)"
    if step.kind not in REPORT_STEPS and step.status in (
        StepStatus.PENDING_RESULT,
        StepStatus.RESULT_AVAILABLE,
    ):
        return f"{step.kind.value} does not produce a report; use scheduled or completed"
    if step.status is StepStatus.SCHEDULED and step.scheduled_for is None:
        return "a scheduled step needs scheduled_for"
    if step.status is StepStatus.COMPLETED and step.completed_on is None:
        return "a completed step needs completed_on"
    return None


def new_step_id(patient_id: str, kind: StepKind) -> str:
    return f"{patient_id}-{kind.value}-{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------- CSV


def _blank(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _date(value: str | None, name: str) -> date | None:
    value = _blank(value)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a date like 2026-03-08, not {value!r}") from exc


def _enum(enum, value: str | None, name: str, *, required: bool = True):
    value = _blank(value)
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return None
    try:
        return enum(value.lower())
    except ValueError as exc:
        allowed = ", ".join(e.value for e in enum)
        raise ValueError(f"{name} must be one of {allowed}, not {value!r}") from exc


def parse_csv(
    text: str, *, known_patients: set[str] = frozenset(), known_steps: set[str] = frozenset()
) -> ImportBatch:
    batch = ImportBatch()
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if reader.fieldnames is None or "record_type" not in reader.fieldnames:
        batch.errors.append(
            ImportIssue("header", "the first row must be a header with a record_type column")
        )
        return batch
    unknown = [c for c in reader.fieldnames if c not in CSV_COLUMNS]
    if unknown:
        batch.errors.append(ImportIssue("header", f"unknown column(s): {', '.join(unknown)}"))
        return batch

    patient_ids = set(known_patients)
    seen_steps = set(known_steps)
    for line, row in enumerate(reader, start=2):
        where = f"row {line}"
        kind = (_blank(row.get("record_type")) or "").lower()
        try:
            if kind == "patient":
                patient, target = _csv_patient(row)
                if patient.id in {p.id for p, _ in batch.patients}:
                    raise ValueError(f"patient {patient.id} appears twice in this file")
                batch.patients.append((patient, target))
                patient_ids.add(patient.id)
            elif kind == "family":
                member = _csv_family(row, patient_ids)
                batch.family.append(member)
            elif kind == "step":
                step = _csv_step(row, patient_ids)
                if step.id in {s.id for s in batch.steps}:
                    raise ValueError(f"step {step.id} appears twice in this file")
                problem = step_problem(step)
                if problem:
                    raise ValueError(problem)
                batch.steps.append(step)
                seen_steps.add(step.id)
            else:
                raise ValueError("record_type must be patient, family or step")
        except ValueError as exc:
            batch.errors.append(ImportIssue(where, str(exc)))
    return batch


def _need(row: dict, name: str) -> str:
    value = _blank(row.get(name))
    if value is None:
        raise ValueError(f"{name} is required")
    return value


def _csv_patient(row: dict) -> tuple[Patient, StepKind | None]:
    try:
        distance = float(_need(row, "home_distance_km"))
    except ValueError as exc:
        raise ValueError("home_distance_km must be a number of kilometres") from exc
    if distance < 0:
        raise ValueError("home_distance_km cannot be negative")
    patient = Patient(
        id=_need(row, "id"),
        name=_blank(row.get("name")) or "",
        abha_number=_blank(row.get("abha_number")),
        home_district=_need(row, "home_district"),
        home_distance_km=distance,
        language=_enum(Language, row.get("language"), "language"),
        caregiver_phone=_need(row, "caregiver_phone"),
        hospital_id=_need(row, "hospital_id"),
    )
    return patient, _enum(StepKind, row.get("plan_target"), "plan_target", required=False)


def _csv_family(row: dict, patient_ids: set[str]) -> FamilyMember:
    patient_id = _need(row, "patient_id")
    if patient_id not in patient_ids:
        raise ValueError(f"patient {patient_id} is not in this file or on record")
    return FamilyMember(
        id=_need(row, "id"),
        patient_id=patient_id,
        role=_enum(FamilyMemberRole, row.get("role"), "role"),
        name=_need(row, "name"),
        phone=_need(row, "phone"),
        preferred_channel=_enum(Channel, row.get("channel"), "channel"),
        language=_enum(Language, row.get("language"), "language"),
    )


def _csv_step(row: dict, patient_ids: set[str]) -> CareStep:
    patient_id = _need(row, "patient_id")
    if patient_id not in patient_ids:
        raise ValueError(f"patient {patient_id} is not in this file or on record")
    kind = _enum(StepKind, row.get("kind"), "kind")
    return CareStep(
        id=_blank(row.get("id")) or new_step_id(patient_id, kind),
        patient_id=patient_id,
        kind=kind,
        status=_enum(StepStatus, row.get("status"), "status"),
        scheduled_for=_date(row.get("scheduled_for"), "scheduled_for"),
        completed_on=_date(row.get("completed_on"), "completed_on"),
        result_available_on=_date(row.get("result_available_on"), "result_available_on"),
        queue=_blank(row.get("queue")),
        resource_id=_blank(row.get("resource_id")),
    )


def csv_template() -> str:
    """A header and one example row of each kind, for a person to start from."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    index = {c: i for i, c in enumerate(CSV_COLUMNS)}

    def row(**values: str) -> list[str]:
        cells = [""] * len(CSV_COLUMNS)
        for key, value in values.items():
            cells[index[key]] = value
        return cells

    writer.writerow(row(record_type="patient", id="P-EXAMPLE", name="Example Family",
                        home_district="Darbhanga", home_distance_km="1850", language="hi",
                        caregiver_phone="+919800000000", hospital_id="TMH-MUM",
                        plan_target="review_consult"))  # fmt: skip
    writer.writerow(row(record_type="family", id="P-EXAMPLE-m1", patient_id="P-EXAMPLE",
                        name="Example Caregiver", role="caregiver_primary",
                        phone="+919800000000", channel="whatsapp", language="hi"))  # fmt: skip
    writer.writerow(row(record_type="step", patient_id="P-EXAMPLE", kind="pathology_report",
                        status="pending_result", completed_on="2026-03-01",
                        queue="pathology_report"))  # fmt: skip
    writer.writerow(row(record_type="step", patient_id="P-EXAMPLE", kind="review_consult",
                        status="scheduled", scheduled_for="2026-03-12",
                        queue="review_consult"))  # fmt: skip
    return out.getvalue()


# ---------------------------------------------------------------- FHIR

_ROLE_BY_RELATIONSHIP = {
    "spouse": FamilyMemberRole.CAREGIVER_PRIMARY,
    "wife": FamilyMemberRole.CAREGIVER_PRIMARY,
    "husband": FamilyMemberRole.CAREGIVER_PRIMARY,
    "child": FamilyMemberRole.CAREGIVER_PRIMARY,
    "son": FamilyMemberRole.CAREGIVER_PRIMARY,
    "daughter": FamilyMemberRole.CAREGIVER_PRIMARY,
    "parent": FamilyMemberRole.CAREGIVER_PRIMARY,
}


def _ref_id(reference: Any, kind: str) -> str | None:
    if isinstance(reference, dict):
        reference = reference.get("reference")
    if isinstance(reference, str):
        match = re.fullmatch(rf"(?:.*/)?{kind}/([^/]+)", reference)
        if match:
            return match.group(1)
    return None


def _human_name(resource: dict) -> str:
    names = resource.get("name") or []
    if names and isinstance(names[0], dict):
        name = names[0]
        if name.get("text"):
            return str(name["text"])
        given = " ".join(name.get("given") or [])
        return f"{given} {name.get('family', '')}".strip()
    return ""


def _phone(resource: dict) -> str | None:
    for telecom in resource.get("telecom") or []:
        if isinstance(telecom, dict) and telecom.get("system") == "phone" and telecom.get("value"):
            return str(telecom["value"])
    return None


def _language_of(resource: dict) -> Language | None:
    for comm in resource.get("communication") or []:
        coding = ((comm.get("language") or {}).get("coding") or [{}])[0]
        code = str(coding.get("code") or "").lower()[:2]
        try:
            return Language(code)
        except ValueError:
            continue
    return None


def _abha(resource: dict) -> str | None:
    for ident in resource.get("identifier") or []:
        text = f"{ident.get('system', '')} {(ident.get('type') or {}).get('text', '')}".lower()
        if "abha" in text or "healthid" in text:
            value = ident.get("value")
            return str(value) if value else None
    return None


def parse_fhir_bundle(
    bundle: dict,
    *,
    hospital_id: str,
    default_distance_km: float | None = None,
    default_language: Language = Language.HINDI,
    known_patients: set[str] = frozenset(),
) -> ImportBatch:
    """Patient, RelatedPerson, Appointment and DiagnosticReport entries.

    A FHIR Patient says nothing about how far the family lives from the
    hospital, so the distance comes from an extension on the resource or from
    `default_distance_km`; with neither, that patient is an error rather than a
    zero that would quietly look like "lives next door".
    """
    batch = ImportBatch()
    if bundle.get("resourceType") != "Bundle":
        batch.errors.append(ImportIssue("bundle", "expected a FHIR Bundle"))
        return batch
    entries = [
        e["resource"]
        for e in bundle.get("entry") or []
        if isinstance(e, dict) and isinstance(e.get("resource"), dict)
    ]

    patient_ids = set(known_patients)
    for resource in (r for r in entries if r.get("resourceType") == "Patient"):
        pid = str(resource.get("id") or "")
        where = f"Patient/{pid or '?'}"
        distance = default_distance_km
        for ext in resource.get("extension") or []:
            if ext.get("url") == DISTANCE_EXTENSION and "valueDecimal" in ext:
                distance = float(ext["valueDecimal"])
        phone = _phone(resource)
        address = (resource.get("address") or [{}])[0]
        district = address.get("district") or address.get("city")
        problems = [
            m
            for ok, m in (
                (pid, "no id"),
                (phone, "no phone number in telecom"),
                (district, "no address.district"),
                (distance is not None, "no home distance (extension or default_distance_km)"),
            )
            if not ok
        ]
        if problems:
            batch.errors.append(ImportIssue(where, "; ".join(problems)))
            continue
        batch.patients.append(
            (
                Patient(
                    id=pid,
                    name=_human_name(resource),
                    abha_number=_abha(resource),
                    home_district=str(district),
                    home_distance_km=float(distance),
                    language=_language_of(resource) or default_language,
                    caregiver_phone=phone,
                    hospital_id=hospital_id,
                ),
                None,
            )
        )
        patient_ids.add(pid)

    for resource in (r for r in entries if r.get("resourceType") == "RelatedPerson"):
        where = f"RelatedPerson/{resource.get('id', '?')}"
        pid = _ref_id(resource.get("patient"), "Patient")
        phone = _phone(resource)
        if pid not in patient_ids or not phone:
            batch.errors.append(
                ImportIssue(where, "needs a known patient reference and a phone number")
            )
            continue
        relationship = (
            ((resource.get("relationship") or [{}])[0].get("text") or "").lower()
        )
        batch.family.append(
            FamilyMember(
                id=f"{pid}-{resource.get('id')}",
                patient_id=pid,
                role=_ROLE_BY_RELATIONSHIP.get(relationship, FamilyMemberRole.CAREGIVER_SECONDARY),
                name=_human_name(resource) or relationship or "family member",
                phone=phone,
                preferred_channel=Channel.WHATSAPP,
                language=_language_of(resource) or default_language,
            )
        )

    step_types = ("Appointment", "DiagnosticReport")
    for resource in (r for r in entries if r.get("resourceType") in step_types):
        where = f"{resource['resourceType']}/{resource.get('id', '?')}"
        pid = _ref_id(resource.get("subject"), "Patient")
        if pid is None:
            for part in resource.get("participant") or []:
                pid = pid or _ref_id((part or {}).get("actor"), "Patient")
        if pid not in patient_ids:
            batch.errors.append(ImportIssue(where, "does not reference a known Patient"))
            continue
        step = to_care_step(resource, pid)
        if step is None:
            batch.skipped.append(
                ImportIssue(where, "not a step we plan around, or a status we do not map")
            )
            continue
        problem = step_problem(step)
        if problem:
            batch.errors.append(ImportIssue(where, problem))
            continue
        batch.steps.append(step)
    return batch
