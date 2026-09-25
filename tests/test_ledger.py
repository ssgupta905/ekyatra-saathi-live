from __future__ import annotations

from dataclasses import replace

from saathi.domain.enums import SourceSystem
from saathi.ledger.evidence import GENESIS_HASH, InMemoryEvidenceLedger


def _ledger(n=3):
    ledger = InMemoryEvidenceLedger()
    for i in range(n):
        ledger.record(
            patient_id="P0001",
            source=SourceSystem.HOSPITAL_FEED,
            source_record_id=f"rec-{i}",
            claim=f"scan is completed ({i})",
        )
    return ledger


def test_empty_ledger_starts_at_genesis():
    assert InMemoryEvidenceLedger().head_hash == GENESIS_HASH


def test_chain_verifies():
    assert _ledger().verify() is True


def test_entries_are_chained_to_their_predecessor():
    ledger = _ledger()
    entries = ledger.for_patient("P0001")
    assert entries[0].previous_hash == GENESIS_HASH
    # Deliberately unequal lengths: this pairs each entry with its successor.
    for previous, current in zip(entries, entries[1:], strict=False):
        assert current.previous_hash == previous.entry_hash


def test_tampering_with_an_entry_breaks_verification():
    """Rewriting history is the attack the chain exists to make visible."""
    ledger = _ledger()
    ledger._entries[1] = replace(ledger._entries[1], claim="scan is result_available")
    assert ledger.verify() is False


def test_refs_resolve_only_to_their_own_entry():
    ledger = _ledger()
    entry = ledger.for_patient("P0001")[0]
    assert ledger.resolve_all([entry.ref()]) is True

    forged = entry.ref().model_copy(update={"source_record_id": "rec-999"})
    assert ledger.resolve_all([forged]) is False


def test_patient_scoping():
    ledger = _ledger()
    ledger.record("P0002", SourceSystem.ABDM, "rec-x", "biopsy is completed")
    assert len(ledger.for_patient("P0001")) == 3
    assert len(ledger.for_patient("P0002")) == 1
