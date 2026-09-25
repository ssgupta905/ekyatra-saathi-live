"""The evidence ledger.

Every sentence Saathi sends to a family must trace back to a record someone can
open. The ledger is the append-only store of those records, hash-chained so that
a message's provenance can be audited after the fact and so that tampering with
an earlier entry invalidates every entry after it.

Nothing here stores report *content*. An entry says "pathology report for step
S became available on the 9th, per ABDM record R" — never what it said.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from ..domain.enums import SourceSystem
from ..domain.models import EvidenceRef

GENESIS_HASH = "0" * 64


class LedgerIntegrityError(RuntimeError):
    """Raised when the hash chain does not verify."""


@dataclass(frozen=True)
class LedgerEntry:
    id: str
    patient_id: str
    source: SourceSystem
    source_record_id: str
    #: Short, human-readable statement of the fact. Auditors read this.
    claim: str
    recorded_at: datetime
    previous_hash: str
    entry_hash: str
    metadata: dict = field(default_factory=dict)

    def ref(self) -> EvidenceRef:
        return EvidenceRef(
            ledger_id=self.id,
            source=self.source,
            source_record_id=self.source_record_id,
        )


def _hash_entry(
    entry_id: str,
    patient_id: str,
    source: SourceSystem,
    source_record_id: str,
    claim: str,
    recorded_at: datetime,
    previous_hash: str,
    metadata: dict,
) -> str:
    payload = json.dumps(
        {
            "id": entry_id,
            "patient_id": patient_id,
            "source": source.value,
            "source_record_id": source_record_id,
            "claim": claim,
            "recorded_at": recorded_at.isoformat(),
            "previous_hash": previous_hash,
            "metadata": metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EvidenceLedger(Protocol):
    def record(
        self,
        patient_id: str,
        source: SourceSystem,
        source_record_id: str,
        claim: str,
        metadata: dict | None = None,
    ) -> LedgerEntry: ...

    def get(self, ledger_id: str) -> LedgerEntry | None: ...

    def for_patient(self, patient_id: str) -> tuple[LedgerEntry, ...]: ...

    def verify(self) -> bool: ...


class InMemoryEvidenceLedger:
    """Reference ledger. The Postgres-backed one shares this interface."""

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []
        self._by_id: dict[str, LedgerEntry] = {}

    @property
    def head_hash(self) -> str:
        return self._entries[-1].entry_hash if self._entries else GENESIS_HASH

    def record(
        self,
        patient_id: str,
        source: SourceSystem,
        source_record_id: str,
        claim: str,
        metadata: dict | None = None,
    ) -> LedgerEntry:
        entry_id = str(uuid.uuid4())
        recorded_at = datetime.now(UTC)
        previous_hash = self.head_hash
        meta = dict(metadata or {})
        entry = LedgerEntry(
            id=entry_id,
            patient_id=patient_id,
            source=source,
            source_record_id=source_record_id,
            claim=claim,
            recorded_at=recorded_at,
            previous_hash=previous_hash,
            entry_hash=_hash_entry(
                entry_id,
                patient_id,
                source,
                source_record_id,
                claim,
                recorded_at,
                previous_hash,
                meta,
            ),
            metadata=meta,
        )
        self._entries.append(entry)
        self._by_id[entry_id] = entry
        return entry

    def get(self, ledger_id: str) -> LedgerEntry | None:
        return self._by_id.get(ledger_id)

    def for_patient(self, patient_id: str) -> tuple[LedgerEntry, ...]:
        return tuple(e for e in self._entries if e.patient_id == patient_id)

    def verify(self) -> bool:
        """Recompute the chain. False means an entry was altered or reordered."""
        previous = GENESIS_HASH
        for entry in self._entries:
            if entry.previous_hash != previous:
                return False
            expected = _hash_entry(
                entry.id,
                entry.patient_id,
                entry.source,
                entry.source_record_id,
                entry.claim,
                entry.recorded_at,
                entry.previous_hash,
                entry.metadata,
            )
            if expected != entry.entry_hash:
                return False
            previous = entry.entry_hash
        return True

    def resolve_all(self, refs: Iterable[EvidenceRef]) -> bool:
        """True when every ref points at an entry that exists and matches."""
        for ref in refs:
            entry = self.get(ref.ledger_id)
            if entry is None:
                return False
            if entry.source != ref.source or entry.source_record_id != ref.source_record_id:
                return False
        return True
