"""Where a family's onboarding details live.

Kept apart from `RecordStore` on purpose: a family's background, documents and
self-reported medical history are not what the planner works from, and nothing
in the planning path is given this store.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.profile import Admission, DocumentRecord


class OnboardingStore(Protocol):
    def section(self, patient_id: str, name: str) -> tuple[dict, str, str] | None:
        """(the saved fields, who saved them, when as ISO text), or None if never saved."""
        ...

    def save_section(self, patient_id: str, name: str, data: dict, saved_by: str) -> None: ...

    def saved_sections(self, patient_id: str) -> frozenset[str]: ...

    def documents(self, patient_id: str) -> tuple[DocumentRecord, ...]: ...

    def save_document(self, record: DocumentRecord, content: bytes) -> None: ...

    def document(self, document_id: str) -> tuple[DocumentRecord, bytes] | None: ...

    def verify_document(self, document_id: str, by: str) -> DocumentRecord | None: ...

    def admissions(self, patient_id: str) -> tuple[Admission, ...]: ...

    def save_admission(self, admission: Admission) -> None: ...

    def activation(self, patient_id: str) -> tuple[str, str] | None:
        """(who activated the family, when), or None."""
        ...

    def activate(self, patient_id: str, by: str) -> None: ...
