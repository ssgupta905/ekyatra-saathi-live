"""Spends over SQLAlchemy. Same database as the records; migrated with them."""

from __future__ import annotations

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from ...db.tables import SpendEntryRow, StatedLimitRow
from ...domain.spends import SpendEntry, SpendSource, StatedLimit


class SqlSpendStore:
    def __init__(self, url: str) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self._engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)

    def close(self) -> None:
        self._engine.dispose()

    def save(self, entry: SpendEntry) -> SpendEntry:
        with self._sessions.begin() as db:
            row = db.get(SpendEntryRow, entry.id)
            if row is None:
                row = SpendEntryRow(id=entry.id, patient_id=entry.patient_id)
                db.add(row)
            row.source = entry.source.value
            row.source_ref = entry.source_ref
            row.payload_json = entry.model_dump_json()
        return entry

    def get(self, patient_id: str, entry_id: str) -> SpendEntry | None:
        with self._sessions() as db:
            row = db.get(SpendEntryRow, entry_id)
            if row is None or row.patient_id != patient_id:
                return None
            return SpendEntry.model_validate_json(row.payload_json)

    def by_id(self, entry_id: str) -> SpendEntry | None:
        with self._sessions() as db:
            row = db.get(SpendEntryRow, entry_id)
            return SpendEntry.model_validate_json(row.payload_json) if row else None

    def entries(self, patient_id: str) -> tuple[SpendEntry, ...]:
        with self._sessions() as db:
            rows = db.scalars(select(SpendEntryRow).where(SpendEntryRow.patient_id == patient_id))
            found = [SpendEntry.model_validate_json(r.payload_json) for r in rows]
        return tuple(sorted(found, key=lambda e: (e.on, e.created_at)))

    def by_source(self, source: SpendSource, source_ref: str) -> SpendEntry | None:
        with self._sessions() as db:
            row = db.scalars(
                select(SpendEntryRow).where(
                    SpendEntryRow.source == source.value, SpendEntryRow.source_ref == source_ref
                )
            ).first()
            return SpendEntry.model_validate_json(row.payload_json) if row else None

    def patients(self) -> tuple[str, ...]:
        with self._sessions() as db:
            spent = set(db.scalars(select(SpendEntryRow.patient_id).distinct()))
            limited = set(db.scalars(select(StatedLimitRow.patient_id)))
        return tuple(sorted(spent | limited))

    def save_limit(self, limit: StatedLimit) -> None:
        with self._sessions.begin() as db:
            row = db.get(StatedLimitRow, limit.patient_id)
            if row is None:
                row = StatedLimitRow(patient_id=limit.patient_id)
                db.add(row)
            row.payload_json = limit.model_dump_json()

    def limit(self, patient_id: str) -> StatedLimit | None:
        with self._sessions() as db:
            row = db.get(StatedLimitRow, patient_id)
            return StatedLimit.model_validate_json(row.payload_json) if row else None

    def clear(self, patient_id: str) -> None:
        with self._sessions.begin() as db:
            db.execute(delete(SpendEntryRow).where(SpendEntryRow.patient_id == patient_id))
            db.execute(delete(StatedLimitRow).where(StatedLimitRow.patient_id == patient_id))
