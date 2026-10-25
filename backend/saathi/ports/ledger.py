"""The evidence ledger as the application sees it."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from ..domain.enums import SourceSystem
from ..domain.ledger import LedgerEntry
from ..domain.models import EvidenceRef


class EvidenceLedger(Protocol):
    @property
    def head_hash(self) -> str: ...

    def record(
        self,
        patient_id: str,
        source: SourceSystem,
        source_record_id: str,
        claim: str,
        metadata: dict | None = None,
    ) -> LedgerEntry: ...

    def record_once(
        self,
        patient_id: str,
        source: SourceSystem,
        source_record_id: str,
        claim: str,
        metadata: dict | None = None,
    ) -> LedgerEntry: ...

    def get(self, ledger_id: str) -> LedgerEntry | None: ...

    def for_patient(self, patient_id: str) -> tuple[LedgerEntry, ...]: ...

    def all_entries(
        self, source: SourceSystem | None = None, since: datetime | None = None
    ) -> tuple[LedgerEntry, ...]: ...

    def size(self) -> int: ...

    def verify(self) -> bool: ...

    def resolve_all(self, refs: Iterable[EvidenceRef]) -> bool: ...
