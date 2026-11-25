"""Spends in memory: the simulated world, and tests."""

from __future__ import annotations

from ...domain.spends import SpendEntry, SpendSource, StatedLimit


class MemorySpendStore:
    def __init__(self) -> None:
        self._entries: dict[str, SpendEntry] = {}
        self._limits: dict[str, StatedLimit] = {}

    def save(self, entry: SpendEntry) -> SpendEntry:
        self._entries[entry.id] = entry
        return entry

    def get(self, patient_id: str, entry_id: str) -> SpendEntry | None:
        entry = self._entries.get(entry_id)
        return entry if entry is not None and entry.patient_id == patient_id else None

    def by_id(self, entry_id: str) -> SpendEntry | None:
        return self._entries.get(entry_id)

    def entries(self, patient_id: str) -> tuple[SpendEntry, ...]:
        found = [e for e in self._entries.values() if e.patient_id == patient_id]
        return tuple(sorted(found, key=lambda e: (e.on, e.created_at)))

    def by_source(self, source: SpendSource, source_ref: str) -> SpendEntry | None:
        return next(
            (
                e
                for e in self._entries.values()
                if e.source is source and e.source_ref == source_ref
            ),
            None,
        )

    def patients(self) -> tuple[str, ...]:
        return tuple(sorted({e.patient_id for e in self._entries.values()} | set(self._limits)))

    def save_limit(self, limit: StatedLimit) -> None:
        self._limits[limit.patient_id] = limit

    def limit(self, patient_id: str) -> StatedLimit | None:
        return self._limits.get(patient_id)

    def clear(self, patient_id: str) -> None:
        self._entries = {k: e for k, e in self._entries.items() if e.patient_id != patient_id}
        self._limits.pop(patient_id, None)
