"""ABDM / FHIR R4 client.

The hard boundary of this whole project lives in this file. ABDM will happily
return a DiagnosticReport with results in it. Saathi must read only whether the
report *exists*, and discard everything else before it reaches any other module.

`_to_status` is the filter. It takes a FHIR resource and returns a status enum.
There is no code path from a FHIR payload to a message body.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

import httpx

from ..domain.enums import StepKind, StepStatus
from ..domain.models import CareStep

logger = logging.getLogger(__name__)

#: FHIR DiagnosticReport.status -> our status vocabulary.
_REPORT_STATUS = {
    "registered": StepStatus.PENDING_RESULT,
    "partial": StepStatus.PENDING_RESULT,
    "preliminary": StepStatus.PENDING_RESULT,
    "final": StepStatus.RESULT_AVAILABLE,
    "amended": StepStatus.RESULT_AVAILABLE,
    "corrected": StepStatus.RESULT_AVAILABLE,
    "cancelled": StepStatus.CANCELLED,
    "entered-in-error": StepStatus.CANCELLED,
}

#: FHIR Appointment.status -> our status vocabulary.
_APPOINTMENT_STATUS = {
    "proposed": StepStatus.NOT_SCHEDULED,
    "pending": StepStatus.NOT_SCHEDULED,
    "booked": StepStatus.SCHEDULED,
    "arrived": StepStatus.SCHEDULED,
    "checked-in": StepStatus.SCHEDULED,
    "fulfilled": StepStatus.COMPLETED,
    "cancelled": StepStatus.CANCELLED,
    "noshow": StepStatus.CANCELLED,
}

#: LOINC/SNOMED-ish code fragments mapped to the steps we plan around. The pilot
#: replaces this with the treating hospital's own service catalogue.
#:
#: Ordered most-specific-first and matched in order: "Follow-up consultation"
#: contains both "follow-up" and "consultation", and it is a review consult, not
#: a first consult. Getting that backwards would make the planner think a
#: prerequisite-heavy visit had no prerequisites at all.
_CODE_TO_KIND: tuple[tuple[str, StepKind], ...] = (
    ("follow-up", StepKind.REVIEW_CONSULT),
    ("follow up", StepKind.REVIEW_CONSULT),
    ("review", StepKind.REVIEW_CONSULT),
    ("histopath", StepKind.PATHOLOGY_REPORT),
    ("pathology", StepKind.PATHOLOGY_REPORT),
    ("biopsy", StepKind.BIOPSY),
    ("ct", StepKind.RADIOLOGY_REPORT),
    ("mri", StepKind.RADIOLOGY_REPORT),
    ("pet", StepKind.RADIOLOGY_REPORT),
    ("imaging", StepKind.RADIOLOGY_REPORT),
    ("haematology", StepKind.BLOODS),
    ("cbc", StepKind.BLOODS),
    ("consultation", StepKind.CONSULT),
    ("consult", StepKind.CONSULT),
)


def _text_of(resource: dict[str, Any]) -> str:
    """Concatenate only the coding *labels* — never `valueQuantity`, never
    `conclusion`, never `presentedForm`."""
    code = resource.get("code", {})
    parts = [code.get("text", "")]
    for coding in code.get("coding", []):
        parts.append(coding.get("display", ""))
        parts.append(coding.get("code", ""))
    return " ".join(p for p in parts if p).lower()


def _classify(resource: dict[str, Any]) -> StepKind | None:
    haystack = _text_of(resource)
    for fragment, kind in _CODE_TO_KIND:
        if fragment in haystack:
            return kind
    return None


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def to_care_step(resource: dict[str, Any], patient_id: str) -> CareStep | None:
    """Project a FHIR resource down to a `CareStep`, dropping all content.

    Returns None for resources we cannot classify — being unable to read a
    record is safer than guessing what it was.
    """
    kind = _classify(resource)
    if kind is None:
        return None

    resource_type = resource.get("resourceType")
    raw_status = (resource.get("status") or "").lower()

    if resource_type == "DiagnosticReport":
        status = _REPORT_STATUS.get(raw_status)
        issued = _parse_date(resource.get("issued"))
        completed = _parse_date(resource.get("effectiveDateTime"))
    elif resource_type == "Appointment":
        status = _APPOINTMENT_STATUS.get(raw_status)
        issued = None
        completed = _parse_date(resource.get("start"))
    else:
        return None

    if status is None:
        logger.debug("unmapped %s status %r", resource_type, raw_status)
        return None

    return CareStep(
        id=f"{resource_type}/{resource.get('id')}",
        patient_id=patient_id,
        kind=kind,
        status=status,
        scheduled_for=completed if resource_type == "Appointment" else None,
        completed_on=completed,
        result_available_on=issued if status is StepStatus.RESULT_AVAILABLE else None,
        queue=_queue_of(resource, kind),
    )


def _queue_of(resource: dict[str, Any], kind: StepKind) -> str:
    """Queue key used to look up turnaround history. One per department."""
    performer = resource.get("performer") or []
    if performer and isinstance(performer[0], dict):
        display = performer[0].get("display")
        if display:
            return f"{kind.value}:{display}".lower()
    return kind.value


class ABDMClient:
    """Thin FHIR R4 reader. Every response passes through `to_care_step`."""

    def __init__(self, base_url: str, token: str, timeout: float = 15.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/fhir+json"},
            timeout=timeout,
        )

    async def care_steps(self, abha_id: str, patient_id: str) -> tuple[CareStep, ...]:
        steps: list[CareStep] = []
        for resource_type in ("Appointment", "DiagnosticReport"):
            bundle = await self._fetch(resource_type, abha_id)
            steps.extend(self._project(bundle, patient_id))
        return tuple(steps)

    async def _fetch(self, resource_type: str, abha_id: str) -> dict[str, Any]:
        response = await self._client.get(
            f"/{resource_type}", params={"patient": abha_id, "_count": 100}
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _project(bundle: dict[str, Any], patient_id: str) -> Iterable[CareStep]:
        for entry in bundle.get("entry", []):
            resource = entry.get("resource")
            if not isinstance(resource, dict):
                continue
            step = to_care_step(resource, patient_id)
            if step is not None:
                yield step

    async def aclose(self) -> None:
        await self._client.aclose()
