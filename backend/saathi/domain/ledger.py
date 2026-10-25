"""The evidence ledger's data model and its hash rule.

Pure: no storage, no clock, no locking. Every ledger implementation — memory
today, SQL next — builds entries and checks chains with these functions, so
"what makes an entry valid" is written down once and cannot drift between
backends.

Nothing here stores report *content*. An entry says "pathology report for step
S became available on the 9th, per ABDM record R" — never what it said.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from .enums import SourceSystem
from .models import EvidenceRef

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


def hash_entry(
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


def seal(
    entry_id: str,
    patient_id: str,
    source: SourceSystem,
    source_record_id: str,
    claim: str,
    recorded_at: datetime,
    previous_hash: str,
    metadata: dict | None = None,
) -> LedgerEntry:
    """Build an entry chained after `previous_hash`."""
    meta = dict(metadata or {})
    return LedgerEntry(
        id=entry_id,
        patient_id=patient_id,
        source=source,
        source_record_id=source_record_id,
        claim=claim,
        recorded_at=recorded_at,
        previous_hash=previous_hash,
        entry_hash=hash_entry(
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


def verify_chain(entries: Iterable[LedgerEntry]) -> bool:
    """Recompute the chain. False means an entry was altered or reordered."""
    previous = GENESIS_HASH
    for entry in entries:
        if entry.previous_hash != previous:
            return False
        expected = hash_entry(
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
