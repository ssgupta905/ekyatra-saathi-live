"""The evidence ledger, kept in a database.

The in-memory ledger is the reference; this one loads the whole chain at start
and writes every new entry through before it joins the in-memory chain. Reads are
therefore as fast as before, and a restart brings back exactly what was written,
which is the point of an audit trail.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from ...db.tables import LedgerRow
from ...domain.enums import SourceSystem
from ...domain.ledger import GENESIS_HASH, LedgerEntry
from ...ledger.evidence import InMemoryEvidenceLedger


class SqlEvidenceLedger(InMemoryEvidenceLedger):
    def __init__(self, url: str) -> None:
        super().__init__()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self._engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)
        self._load()

    def close(self) -> None:
        self._engine.dispose()

    def _load(self) -> None:
        with self._sessions() as db:
            # Follow the chain from its start rather than trusting any column's
            # order: the links are what define the order, on any database.
            by_previous = {row.previous_hash: row for row in db.scalars(select(LedgerRow))}
            ordered = []
            link = GENESIS_HASH
            while link in by_previous:
                row = by_previous[link]
                ordered.append(row)
                link = row.entry_hash
            for row in ordered:
                entry = LedgerEntry(
                    id=row.id,
                    patient_id=row.patient_id,
                    source=SourceSystem(row.source),
                    source_record_id=row.source_record_id,
                    claim=row.claim,
                    recorded_at=datetime.fromisoformat(row.recorded_at_iso),
                    previous_hash=row.previous_hash,
                    entry_hash=row.entry_hash,
                    metadata=json.loads(row.metadata_json or "{}"),
                )
                self._entries.append(entry)
                self._by_id[entry.id] = entry
                self._latest[(entry.patient_id, entry.source_record_id)] = entry

    def _persist(self, entry: LedgerEntry) -> None:
        with self._sessions.begin() as db:
            db.add(
                LedgerRow(
                    id=entry.id,
                    patient_id=entry.patient_id,
                    source=entry.source.value,
                    source_record_id=entry.source_record_id,
                    claim=entry.claim,
                    recorded_at=entry.recorded_at,
                    recorded_at_iso=entry.recorded_at.isoformat(),
                    previous_hash=entry.previous_hash,
                    entry_hash=entry.entry_hash,
                    metadata_json=json.dumps(entry.metadata, sort_keys=True),
                )
            )
