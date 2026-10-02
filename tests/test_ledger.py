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


def test_all_entries_returns_entries_across_patients():
    ledger = InMemoryEvidenceLedger()
    ledger.record(patient_id="P0001", source=SourceSystem.HOSPITAL_FEED,
                   source_record_id="r1", claim="a")
    ledger.record(patient_id="P0002", source=SourceSystem.NAVIGATOR,
                   source_record_id="r2", claim="b")
    all_rows = ledger.all_entries()
    assert {e.patient_id for e in all_rows} == {"P0001", "P0002"}


def test_all_entries_filters_by_source():
    ledger = InMemoryEvidenceLedger()
    ledger.record(patient_id="P0001", source=SourceSystem.HOSPITAL_FEED,
                   source_record_id="r1", claim="a")
    ledger.record(patient_id="P0001", source=SourceSystem.NAVIGATOR,
                   source_record_id="r2", claim="b")
    filtered = ledger.all_entries(source=SourceSystem.NAVIGATOR)
    assert len(filtered) == 1
    assert filtered[0].source is SourceSystem.NAVIGATOR


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


def test_record_once_does_not_restate_an_unchanged_fact():
    """Re-planning an unchanged patient must not grow the chain.

    The live demo re-plans every patient every simulated day. Without this the
    one entry that matters is buried under hundreds of identical copies.
    """
    ledger = InMemoryEvidenceLedger()
    first = ledger.record_once(
        "P0001", SourceSystem.ABDM, "rec-1", "pathology_report is pending_result"
    )
    again = ledger.record_once(
        "P0001", SourceSystem.ABDM, "rec-1", "pathology_report is pending_result"
    )

    assert again.id == first.id
    assert len(ledger.for_patient("P0001")) == 1
    assert ledger.verify() is True


def test_record_once_appends_when_the_fact_actually_changes():
    ledger = InMemoryEvidenceLedger()
    ledger.record_once(
        "P0001", SourceSystem.ABDM, "rec-1", "pathology_report is pending_result"
    )
    changed = ledger.record_once(
        "P0001", SourceSystem.ABDM, "rec-1", "pathology_report is result_available"
    )

    entries = ledger.for_patient("P0001")
    assert len(entries) == 2
    assert entries[-1].id == changed.id
    assert entries[-1].previous_hash == entries[0].entry_hash
    assert ledger.verify() is True


def test_record_once_separates_patients_sharing_a_record_id():
    ledger = InMemoryEvidenceLedger()
    ledger.record_once("P0001", SourceSystem.ABDM, "rec-1", "scan is completed")
    ledger.record_once("P0002", SourceSystem.ABDM, "rec-1", "scan is completed")

    assert len(ledger.for_patient("P0001")) == 1
    assert len(ledger.for_patient("P0002")) == 1


def test_record_once_notices_a_metadata_change():
    """Same claim, different supporting detail, is still a new fact."""
    ledger = InMemoryEvidenceLedger()
    ledger.record_once(
        "P0001", SourceSystem.HOSPITAL_FEED, "rec-1", "review_consult is scheduled",
        {"scheduled_for": "2026-10-04"},
    )
    ledger.record_once(
        "P0001", SourceSystem.HOSPITAL_FEED, "rec-1", "review_consult is scheduled",
        {"scheduled_for": "2026-10-11"},
    )
    assert len(ledger.for_patient("P0001")) == 2
