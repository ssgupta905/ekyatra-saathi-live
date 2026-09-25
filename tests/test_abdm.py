"""The scope boundary: FHIR content must never survive ingestion."""

from __future__ import annotations

from saathi.domain.enums import StepKind, StepStatus
from saathi.ingest.abdm import to_care_step


def _report(status="final", with_content=True):
    resource = {
        "resourceType": "DiagnosticReport",
        "id": "rep-1",
        "status": status,
        "effectiveDateTime": "2026-03-01T09:00:00Z",
        "issued": "2026-03-08T14:30:00Z",
        "code": {"text": "Histopathology report", "coding": [{"display": "Histopath"}]},
        "performer": [{"display": "TMH Pathology"}],
    }
    if with_content:
        resource["conclusion"] = "CONFIDENTIAL CLINICAL FINDING"
        resource["presentedForm"] = [{"data": "base64pdf"}]
        resource["result"] = [{"reference": "Observation/1"}]
    return resource


def test_final_report_maps_to_result_available():
    step = to_care_step(_report(), "P0001")
    assert step is not None
    assert step.kind is StepKind.PATHOLOGY_REPORT
    assert step.status is StepStatus.RESULT_AVAILABLE


def test_preliminary_report_is_still_pending():
    step = to_care_step(_report(status="preliminary"), "P0001")
    assert step.status is StepStatus.PENDING_RESULT


def test_report_content_is_dropped_entirely():
    """The single most important assertion in this repository."""
    step = to_care_step(_report(with_content=True), "P0001")
    serialised = step.model_dump_json()
    assert "CONFIDENTIAL" not in serialised
    assert "base64pdf" not in serialised
    assert "Observation" not in serialised


def test_queue_is_derived_from_the_performing_department():
    step = to_care_step(_report(), "P0001")
    assert step.queue == "pathology_report:tmh pathology"


def test_unclassifiable_resource_is_skipped():
    assert to_care_step(
        {"resourceType": "DiagnosticReport", "id": "x", "status": "final",
         "code": {"text": "something we have no mapping for"}},
        "P0001",
    ) is None


def test_appointment_maps_to_a_scheduled_step():
    step = to_care_step(
        {
            "resourceType": "Appointment",
            "id": "appt-1",
            "status": "booked",
            "start": "2026-03-12T10:00:00Z",
            "code": {"text": "Follow-up consultation"},
        },
        "P0001",
    )
    assert step.kind is StepKind.REVIEW_CONSULT
    assert step.status is StepStatus.SCHEDULED
    assert step.scheduled_for.isoformat() == "2026-03-12"


def test_unknown_status_is_skipped_rather_than_guessed():
    assert to_care_step(_report(status="who-knows"), "P0001") is None
