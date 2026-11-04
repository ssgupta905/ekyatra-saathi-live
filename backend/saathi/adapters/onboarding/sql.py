"""Onboarding details over SQLAlchemy. Same database as the records; migrated with them."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from ...db.tables import AdmissionRow, FamilyProfileRow, ProfileDocumentRow
from ...domain.profile import Admission, DocumentRecord


class SqlOnboardingStore:
    def __init__(self, url: str) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self._engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)

    def close(self) -> None:
        self._engine.dispose()

    # ---------------- sections ----------------

    def _row(self, db, patient_id: str) -> FamilyProfileRow:
        row = db.get(FamilyProfileRow, patient_id)
        if row is None:
            row = FamilyProfileRow(patient_id=patient_id, sections_json="{}")
            db.add(row)
        return row

    def section(self, patient_id: str, name: str) -> tuple[dict, str, str] | None:
        with self._sessions() as db:
            row = db.get(FamilyProfileRow, patient_id)
            saved = json.loads(row.sections_json).get(name) if row else None
            return (saved["data"], saved["by"], saved["at"]) if saved else None

    def save_section(self, patient_id: str, name: str, data: dict, saved_by: str) -> None:
        with self._sessions.begin() as db:
            row = self._row(db, patient_id)
            sections = json.loads(row.sections_json)
            sections[name] = {
                "data": data,
                "by": saved_by,
                "at": datetime.now(UTC).isoformat(),
            }
            row.sections_json = json.dumps(sections, sort_keys=True)

    def saved_sections(self, patient_id: str) -> frozenset[str]:
        with self._sessions() as db:
            row = db.get(FamilyProfileRow, patient_id)
            return frozenset(json.loads(row.sections_json)) if row else frozenset()

    # ---------------- documents ----------------

    def documents(self, patient_id: str) -> tuple[DocumentRecord, ...]:
        with self._sessions() as db:
            return tuple(
                DocumentRecord.model_validate_json(r.meta_json)
                for r in db.scalars(
                    select(ProfileDocumentRow)
                    .where(ProfileDocumentRow.patient_id == patient_id)
                    .order_by(ProfileDocumentRow.id)
                )
            )

    def save_document(self, record: DocumentRecord, content: bytes) -> None:
        with self._sessions.begin() as db:
            row = db.get(ProfileDocumentRow, record.id) or ProfileDocumentRow(id=record.id)
            row.patient_id = record.patient_id
            row.meta_json = record.model_dump_json()
            row.content = content
            db.merge(row)

    def document(self, document_id: str) -> tuple[DocumentRecord, bytes] | None:
        with self._sessions() as db:
            row = db.get(ProfileDocumentRow, document_id)
            if row is None:
                return None
            return DocumentRecord.model_validate_json(row.meta_json), bytes(row.content)

    def verify_document(self, document_id: str, by: str) -> DocumentRecord | None:
        with self._sessions.begin() as db:
            row = db.get(ProfileDocumentRow, document_id)
            if row is None:
                return None
            record = DocumentRecord.model_validate_json(row.meta_json).model_copy(
                update={"verified_by": by}
            )
            row.meta_json = record.model_dump_json()
            return record

    # ---------------- admissions ----------------

    def admissions(self, patient_id: str) -> tuple[Admission, ...]:
        with self._sessions() as db:
            return tuple(
                Admission.model_validate_json(r.payload_json)
                for r in db.scalars(
                    select(AdmissionRow)
                    .where(AdmissionRow.patient_id == patient_id)
                    .order_by(AdmissionRow.id)
                )
            )

    def save_admission(self, admission: Admission) -> None:
        with self._sessions.begin() as db:
            row = db.get(AdmissionRow, admission.id) or AdmissionRow(id=admission.id)
            row.patient_id = admission.patient_id
            row.payload_json = admission.model_dump_json()
            db.merge(row)

    # ---------------- activation ----------------

    def activation(self, patient_id: str) -> tuple[str, str] | None:
        with self._sessions() as db:
            row = db.get(FamilyProfileRow, patient_id)
            if row is None or row.activated_at is None:
                return None
            return row.activated_by or "", row.activated_at.isoformat()

    def activate(self, patient_id: str, by: str) -> None:
        with self._sessions.begin() as db:
            row = self._row(db, patient_id)
            row.activated_by = by
            row.activated_at = datetime.now(UTC)
