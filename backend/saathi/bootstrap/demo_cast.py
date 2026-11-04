"""Three scripted families, for walking someone through the whole platform.

Each one starts at a different point in a different story, so one sitting shows
the chain filling in on its own, a vendor failing and staff recovering, and a
second condition on the same engine. Where a family receives its sign-in code is
a parameter, never written here.

Loading is idempotent and doubles as a reset: run again and each family goes back
to where its story starts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..domain.enums import Language, StepKind, StepStatus
from ..domain.models import CareStep, Patient


@dataclass(frozen=True)
class CastMember:
    patient: Patient
    steps: tuple[CareStep, ...]
    #: Organisation ids staff chose for this family, by need (see `PartnersSection`).
    partners: dict[str, str]
    story: str


def _step(pid, kind, status, *, on=None, done=None, released=None, queue=None, resource=None):
    return CareStep(
        id=f"{pid}-{kind.value}", patient_id=pid, kind=kind, status=status, scheduled_for=on,
        completed_on=done, result_available_on=released, queue=queue or kind.value,
        resource_id=resource,
    )


def build_cast(emails: list[str], today: date) -> tuple[CastMember, ...]:
    """The cast, with each family's email taken in order from `emails`."""
    earlier = today - timedelta(days=6)
    pending_since = today - timedelta(days=4)
    done, avail = StepStatus.COMPLETED, StepStatus.RESULT_AVAILABLE

    def patient(pid, name, district, km, pathway, phone, email):
        return Patient(
            id=pid, name=name, home_district=district, home_distance_km=km,
            language=Language.HINDI, caregiver_phone=phone, caregiver_email=email,
            hospital_id="TMH-MUM", pathway_id=pathway, abha_number=f"91-2000-0000-{phone[-4:]}",
        )

    def at(index):
        return emails[index].strip().lower() if index < len(emails) else None

    cast = (
        CastMember(
            patient("DEMO-1", "Anita Sharma", "Gaya", 1010.0, "oncology", "+919000000101", at(0)),
            (
                _step("DEMO-1", StepKind.CONSULT, done, on=earlier, done=earlier),
                _step("DEMO-1", StepKind.BIOPSY, done, on=earlier, done=earlier),
                _step("DEMO-1", StepKind.BLOODS, done, on=earlier, done=earlier),
                _step("DEMO-1", StepKind.SCAN, done, on=earlier, done=earlier),
                _step("DEMO-1", StepKind.PATHOLOGY_REPORT, StepStatus.PENDING_RESULT,
                      done=pending_since, queue="pathology_report"),
                _step("DEMO-1", StepKind.RADIOLOGY_REPORT, avail, done=earlier, released=earlier,
                      queue="radiology_report"),
                _step("DEMO-1", StepKind.REVIEW_CONSULT, StepStatus.SCHEDULED,
                      on=today + timedelta(days=3)),
            ),
            {},
            "A smooth journey: release the pathology report and watch every party answer.",
        ),
        CastMember(
            patient("DEMO-2", "Ravi Kumar", "Patna", 600.0, "oncology", "+919000000102", at(1)),
            (
                _step("DEMO-2", StepKind.CONSULT, done, on=earlier, done=earlier),
                _step("DEMO-2", StepKind.BIOPSY, done, on=earlier, done=earlier),
                _step("DEMO-2", StepKind.BLOODS, done, on=earlier, done=earlier),
                _step("DEMO-2", StepKind.SCAN, done, on=earlier, done=earlier),
                _step("DEMO-2", StepKind.PATHOLOGY_REPORT, avail, done=earlier, released=earlier,
                      queue="pathology_report"),
                _step("DEMO-2", StepKind.RADIOLOGY_REPORT, avail, done=earlier, released=earlier,
                      queue="radiology_report"),
                _step("DEMO-2", StepKind.REVIEW_CONSULT, StepStatus.SCHEDULED,
                      on=today + timedelta(days=3)),
            ),
            {"transport": "cab-uber"},
            "A vendor fails: Uber cannot, staff book another cab, the family is back on track.",
        ),
        CastMember(
            patient(
                "DEMO-3", "Meena Gupta", "Varanasi", 1100.0, "dialysis", "+919000000103", at(2)
            ),
            (
                _step("DEMO-3", StepKind.BLOODS, done, on=earlier, done=earlier),
                _step("DEMO-3", StepKind.NEPHROLOGY_REVIEW, done, on=earlier, done=earlier),
                _step("DEMO-3", StepKind.DIALYSIS_SESSION, StepStatus.SCHEDULED,
                      on=today + timedelta(days=1), resource="DIALYSIS-3"),
            ),
            {},
            "A second condition on the same engine: dialysis, a ride, and a repeating session.",
        ),
    )
    return cast[: max(len(emails), 1)] if emails else cast
