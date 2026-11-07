"""A record store that keeps everything in dictionaries."""

from __future__ import annotations

from ...domain.consent import AccessAttempt, ConsentGrant, ConsentRequest, RecordPointer
from ...domain.enums import StepKind
from ...domain.models import (
    ApprovalDecision,
    CareStep,
    Disruption,
    Patient,
    ReadinessItem,
    Resource,
)
from ...ports.records import StoredOptionSet, StoredRecords, TurnaroundObservation


class MemoryRecordStore:
    def __init__(self) -> None:
        self._patients: dict[str, Patient] = {}
        self._steps: dict[str, dict[str, CareStep]] = {}
        self._resources: dict[str, Resource] = {}
        self._targets: dict[str, StepKind] = {}
        self._turnaround: list[TurnaroundObservation] = []
        self._disruptions: dict[str, Disruption] = {}
        self._readiness: dict[tuple[str, str], ReadinessItem] = {}
        self._option_sets: dict[str, StoredOptionSet] = {}
        self._approvals: dict[str, ApprovalDecision] = {}
        self._family_messages: dict[str, dict] = {}
        self._consent_requests: dict[str, ConsentRequest] = {}
        self._consent_grants: dict[str, ConsentGrant] = {}
        self._pointers: dict[str, RecordPointer] = {}
        self._attempts: dict[str, AccessAttempt] = {}

    def load(self) -> StoredRecords:
        return StoredRecords(
            patients=tuple(self._patients.values()),
            steps={pid: tuple(rows.values()) for pid, rows in self._steps.items()},
            resources=tuple(self._resources.values()),
            plan_targets=dict(self._targets),
            turnaround=tuple(self._turnaround),
            disruptions=tuple(self._disruptions.values()),
            readiness_items=tuple(self._readiness.values()),
            option_sets=tuple(self._option_sets.values()),
            approvals=tuple(self._approvals.values()),
            family_messages=tuple(self._family_messages.values()),
            consent_requests=tuple(self._consent_requests.values()),
            consent_grants=tuple(self._consent_grants.values()),
            record_pointers=tuple(self._pointers.values()),
            access_attempts=tuple(self._attempts.values()),
        )

    def save_patient(self, patient: Patient, plan_target: StepKind | None = None) -> None:
        self._patients[patient.id] = patient
        self._steps.setdefault(patient.id, {})
        if plan_target is not None:
            self._targets[patient.id] = plan_target

    def save_step(self, step: CareStep) -> None:
        self._steps.setdefault(step.patient_id, {})[step.id] = step

    def save_resource(self, resource: Resource) -> None:
        self._resources[resource.id] = resource

    def add_turnaround(self, observation: TurnaroundObservation) -> None:
        self._turnaround.append(observation)

    def save_disruption(self, disruption: Disruption) -> None:
        self._disruptions[disruption.id] = disruption

    def save_readiness_item(self, item: ReadinessItem) -> None:
        self._readiness[(item.patient_id, item.id)] = item

    def delete_readiness_item(self, patient_id: str, item_id: str) -> None:
        self._readiness.pop((patient_id, item_id), None)

    def save_option_set(self, option_set: StoredOptionSet) -> None:
        self._option_sets[option_set.patient_id] = option_set

    def delete_option_set(self, patient_id: str) -> None:
        self._option_sets.pop(patient_id, None)

    def add_family_message(self, row: dict) -> None:
        self._family_messages.setdefault(row["id"], dict(row))

    def clear_family_messages(self, patient_id: str) -> None:
        kept = {k: r for k, r in self._family_messages.items() if r["patient_id"] != patient_id}
        self._family_messages = kept

    def add_approval(self, approval: ApprovalDecision) -> None:
        # Append-only: an approval already on file is never rewritten.
        self._approvals.setdefault(approval.id, approval)

    def save_consent_request(self, request: ConsentRequest) -> None:
        self._consent_requests[request.id] = request

    def save_consent_grant(self, grant: ConsentGrant) -> None:
        self._consent_grants[grant.id] = grant

    def save_record_pointer(self, pointer: RecordPointer) -> None:
        self._pointers[pointer.id] = pointer

    def add_access_attempt(self, attempt: AccessAttempt) -> None:
        self._attempts.setdefault(attempt.id, attempt)
