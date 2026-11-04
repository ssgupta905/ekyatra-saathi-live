"""Onboarding details in dictionaries, for the demo world and tests."""

from __future__ import annotations

from datetime import UTC, datetime

from ...domain.profile import Admission, DocumentRecord


class MemoryOnboardingStore:
    def __init__(self) -> None:
        self._sections: dict[tuple[str, str], tuple[dict, str, str]] = {}
        self._documents: dict[str, tuple[DocumentRecord, bytes]] = {}
        self._admissions: dict[str, Admission] = {}
        self._activations: dict[str, tuple[str, str]] = {}

    def section(self, patient_id: str, name: str) -> tuple[dict, str, str] | None:
        return self._sections.get((patient_id, name))

    def save_section(self, patient_id: str, name: str, data: dict, saved_by: str) -> None:
        self._sections[(patient_id, name)] = (data, saved_by, datetime.now(UTC).isoformat())

    def saved_sections(self, patient_id: str) -> frozenset[str]:
        return frozenset(name for (pid, name) in self._sections if pid == patient_id)

    def documents(self, patient_id: str) -> tuple[DocumentRecord, ...]:
        return tuple(r for r, _ in self._documents.values() if r.patient_id == patient_id)

    def save_document(self, record: DocumentRecord, content: bytes) -> None:
        self._documents[record.id] = (record, content)

    def document(self, document_id: str) -> tuple[DocumentRecord, bytes] | None:
        return self._documents.get(document_id)

    def verify_document(self, document_id: str, by: str) -> DocumentRecord | None:
        found = self._documents.get(document_id)
        if found is None:
            return None
        record = found[0].model_copy(update={"verified_by": by})
        self._documents[document_id] = (record, found[1])
        return record

    def admissions(self, patient_id: str) -> tuple[Admission, ...]:
        return tuple(a for a in self._admissions.values() if a.patient_id == patient_id)

    def save_admission(self, admission: Admission) -> None:
        self._admissions[admission.id] = admission

    def activation(self, patient_id: str) -> tuple[str, str] | None:
        return self._activations.get(patient_id)

    def activate(self, patient_id: str, by: str) -> None:
        self._activations[patient_id] = (by, datetime.now(UTC).isoformat())
