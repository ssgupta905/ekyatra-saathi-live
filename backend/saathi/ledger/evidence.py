"""The in-memory evidence ledger.

Every sentence Saathi sends to a family must trace back to a record someone can
open. The ledger is the append-only store of those records, hash-chained so that
a message's provenance can be audited after the fact and so that tampering with
an earlier entry invalidates every entry after it.

The data model and the hash rule live in `domain/ledger.py`; the port is
`ports/ledger.py`. This is the reference adapter.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from ..domain.enums import SourceSystem
from ..domain.ledger import GENESIS_HASH, LedgerEntry, seal, verify_chain
from ..domain.models import EvidenceRef


class InMemoryEvidenceLedger:
    """Reference ledger. The SQL-backed one shares the `EvidenceLedger` port.

    Appends are serialised by a lock. Planning runs on worker threads while the
    event loop also writes, and an append is read-head-then-write: two writers
    interleaving would both chain onto the same head and fork the chain.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: list[LedgerEntry] = []
        self._by_id: dict[str, LedgerEntry] = {}
        #: Newest entry per (patient, source record). Lets `record_once` tell a
        #: restatement from a genuine change without rescanning the chain.
        self._latest: dict[tuple[str, str], LedgerEntry] = {}

    @property
    def head_hash(self) -> str:
        with self._lock:
            return self._entries[-1].entry_hash if self._entries else GENESIS_HASH

    def record(
        self,
        patient_id: str,
        source: SourceSystem,
        source_record_id: str,
        claim: str,
        metadata: dict | None = None,
    ) -> LedgerEntry:
        with self._lock:
            entry = seal(
                str(uuid.uuid4()),
                patient_id,
                source,
                source_record_id,
                claim,
                datetime.now(UTC),
                self.head_hash,
                metadata,
            )
            self._entries.append(entry)
            self._by_id[entry.id] = entry
            self._latest[(patient_id, source_record_id)] = entry
            return entry

    def record_once(
        self,
        patient_id: str,
        source: SourceSystem,
        source_record_id: str,
        claim: str,
        metadata: dict | None = None,
    ) -> LedgerEntry:
        """Record `claim` unless the newest entry for this record already says it.

        The ledger stays append-only — this does not rewrite history, it declines
        to append a row that asserts nothing new. Planning is idempotent, so
        without this a patient re-planned once per simulated day buries the one
        entry that changed under hundreds of identical copies, and an auditor
        reading the chain learns nothing from it.
        """
        meta = dict(metadata or {})
        with self._lock:
            existing = self._latest.get((patient_id, source_record_id))
            if (
                existing is not None
                and existing.source is source
                and existing.claim == claim
                and existing.metadata == meta
            ):
                return existing
            return self.record(patient_id, source, source_record_id, claim, meta)

    def get(self, ledger_id: str) -> LedgerEntry | None:
        return self._by_id.get(ledger_id)

    def size(self) -> int:
        """Entries in the chain. The live console watches this grow."""
        return len(self._entries)

    def for_patient(self, patient_id: str) -> tuple[LedgerEntry, ...]:
        with self._lock:
            return tuple(e for e in self._entries if e.patient_id == patient_id)

    def all_entries(
        self, source: SourceSystem | None = None, since: datetime | None = None
    ) -> tuple[LedgerEntry, ...]:
        """Every entry across every patient — the admin audit log's read."""
        with self._lock:
            rows = list(self._entries)
        if source is not None:
            rows = [e for e in rows if e.source is source]
        if since is not None:
            rows = [e for e in rows if e.recorded_at >= since]
        return tuple(rows)

    def verify(self) -> bool:
        """Recompute the chain. False means an entry was altered or reordered."""
        with self._lock:
            return verify_chain(list(self._entries))

    def resolve_all(self, refs: Iterable[EvidenceRef]) -> bool:
        """True when every ref points at an entry that exists and matches."""
        for ref in refs:
            entry = self.get(ref.ledger_id)
            if entry is None:
                return False
            if entry.source != ref.source or entry.source_record_id != ref.source_record_id:
                return False
        return True
