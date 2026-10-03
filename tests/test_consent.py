"""Consent has to be a property of the system, not a promise in a policy.

The claim being defended is "Saathi holds a consented index, never the records",
and each half is tested separately: that a pointer *cannot* carry content, and
that nothing resolves without a live grant. The second half is the one that
usually rots — a withdrawal that changes a flag on a screen while the data keeps
flowing is the failure mode, so revocation is tested at the point of read.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError
from saathi.consent.registry import ConsentError, ConsentRegistry
from saathi.domain.consent import (
    AccessOutcome,
    ConsentCapacity,
    ConsentGrant,
    ConsentPurpose,
    RecordPointer,
)
from saathi.domain.enums import Channel, Language, SourceSystem
from saathi.ledger.evidence import InMemoryEvidenceLedger

ABHA = "12-3456-7890-1234"
MUZAFFARPUR = "HBCH-MZP"


@pytest.fixture
def registry() -> ConsentRegistry:
    return ConsentRegistry(ledger=InMemoryEvidenceLedger())


@pytest.fixture
def pointer(registry: ConsentRegistry) -> RecordPointer:
    return registry.add_pointer(
        RecordPointer(
            id="rec-1",
            abha_number=ABHA,
            care_context_id="cc-1",
            test_name="BRCA1 germline panel",
            category="molecular pathology",
            performed_on=date(2026, 3, 4),
            source_name="Tata Memorial Hospital",
            source_system=SourceSystem.ABDM,
            source_reference="tmh/dr/88213",
        )
    )


def _request(registry: ConsentRegistry, **overrides):
    params = {
        "abha_number": ABHA,
        "purpose": ConsentPurpose.RECORD_MOVEMENT,
        "requester_id": MUZAFFARPUR,
        "requester_name": "Homi Bhabha Cancer Hospital, Muzaffarpur",
        "categories": ("molecular pathology",),
        "reason": "radiotherapy moving nearer home",
    }
    return registry.request(**{**params, **overrides})


# ---------------------------------------------------------------- the index


def test_a_pointer_has_no_field_that_could_hold_a_report():
    """The boundary is a property of the type, not a habit."""
    forbidden = {"value", "values", "conclusion", "result", "text", "attachment",
                 "presented_form", "content", "body", "finding", "impression"}
    assert not (forbidden & set(RecordPointer.model_fields)), (
        "RecordPointer grew a field that could carry report content"
    )


def test_a_pointer_rejects_an_extra_field():
    """`extra='forbid'` means a content field cannot be smuggled in at runtime."""
    with pytest.raises(ValidationError):
        RecordPointer(
            id="x", abha_number=ABHA, care_context_id="cc", test_name="t",
            category="c", performed_on=date(2026, 1, 1), source_name="s",
            source_system=SourceSystem.ABDM, source_reference="r",
            conclusion="malignant",
        )


def test_a_navigator_does_not_see_which_panel_was_run(pointer):
    """A timeline is a diagnosis if you read it sideways."""
    navigator = pointer.as_seen_by("navigator")
    assert navigator["test_name"] is None
    assert navigator["redacted"] is True
    assert navigator["category"] == "molecular pathology"

    for role in ("patient", "caregiver", "doctor"):
        assert pointer.as_seen_by(role)["test_name"] == "BRCA1 germline panel"


def test_indexing_a_record_writes_no_content_to_the_ledger(registry, pointer):
    entry = registry.ledger.for_patient(ABHA)[0]
    assert "BRCA1" not in entry.claim
    assert "malignant" not in entry.claim.lower()
    assert entry.claim.startswith("molecular pathology record from")


# ---------------------------------------------------------------- asking


def test_a_request_must_name_what_it_needs(registry):
    """'Everything' is not a purpose."""
    with pytest.raises(ConsentError, match="not a purpose"):
        _request(registry, categories=())


def test_nothing_resolves_before_anyone_answers(registry, pointer):
    _request(registry)
    outcome, resolved = registry.resolve(
        pointer.id, requester_id=MUZAFFARPUR, purpose=ConsentPurpose.RECORD_MOVEMENT
    )
    assert outcome is AccessOutcome.NO_CONSENT
    assert resolved is None


def test_capacity_is_recorded_not_assumed(registry, pointer):
    """Answering the patient's phone does not make somebody their nominee."""
    request = _request(registry)
    grant = registry.grant(
        request.id,
        granted_by="Vikash",
        capacity=ConsentCapacity.NOMINEE,
        channel=Channel.IVR,
    )
    assert grant.capacity is ConsentCapacity.NOMINEE
    assert grant.granted_by == "Vikash"
    claim = registry.ledger.for_patient(ABHA)[-1].claim
    assert "as nominee" in claim
    assert "on ivr" in claim


# ---------------------------------------------------------------- reading


def test_a_live_grant_resolves(registry, pointer):
    request = _request(registry)
    registry.grant(
        request.id, granted_by="Shambhu Prasad",
        capacity=ConsentCapacity.SELF, channel=Channel.IVR,
    )
    outcome, resolved = registry.resolve(
        pointer.id, requester_id=MUZAFFARPUR, purpose=ConsentPurpose.RECORD_MOVEMENT
    )
    assert outcome is AccessOutcome.GRANTED
    assert resolved is not None
    assert resolved.source_reference == "tmh/dr/88213"


def test_withdrawal_stops_the_record_resolving(registry, pointer):
    """The failure mode this exists to prevent: a flag changes, data keeps flowing."""
    request = _request(registry)
    grant = registry.grant(
        request.id, granted_by="Shambhu Prasad",
        capacity=ConsentCapacity.SELF, channel=Channel.IVR,
    )
    assert registry.resolve(
        pointer.id, requester_id=MUZAFFARPUR, purpose=ConsentPurpose.RECORD_MOVEMENT
    )[0] is AccessOutcome.GRANTED

    registry.revoke(grant.id, by="Shambhu Prasad", reason="changed my mind")

    outcome, resolved = registry.resolve(
        pointer.id, requester_id=MUZAFFARPUR, purpose=ConsentPurpose.RECORD_MOVEMENT
    )
    assert outcome is AccessOutcome.REVOKED
    assert resolved is None


def test_an_expired_grant_is_refused_and_says_so(registry, pointer):
    request = _request(registry)
    grant = registry.grant(
        request.id, granted_by="Shambhu Prasad",
        capacity=ConsentCapacity.SELF, channel=Channel.IVR, days=1,
    )
    later = grant.expires_at + timedelta(seconds=1)
    outcome, _ = registry.resolve(
        pointer.id, requester_id=MUZAFFARPUR,
        purpose=ConsentPurpose.RECORD_MOVEMENT, at=later,
    )
    assert outcome is AccessOutcome.EXPIRED


def test_consent_for_one_purpose_does_not_grant_another(registry, pointer):
    """Research is never a condition of care, and care never implies research."""
    care = _request(registry, purpose=ConsentPurpose.CARE_COORDINATION)
    registry.grant(
        care.id, granted_by="Shambhu Prasad",
        capacity=ConsentCapacity.SELF, channel=Channel.IVR,
    )
    outcome, _ = registry.resolve(
        pointer.id, requester_id=MUZAFFARPUR, purpose=ConsentPurpose.RESEARCH
    )
    assert outcome is AccessOutcome.NO_CONSENT


def test_consent_for_one_requester_does_not_grant_another(registry, pointer):
    request = _request(registry)
    registry.grant(
        request.id, granted_by="Shambhu Prasad",
        capacity=ConsentCapacity.SELF, channel=Channel.IVR,
    )
    outcome, _ = registry.resolve(
        pointer.id, requester_id="SOME-OTHER-HOSPITAL",
        purpose=ConsentPurpose.RECORD_MOVEMENT,
    )
    assert outcome is AccessOutcome.NO_CONSENT


def test_a_record_outside_the_agreed_categories_is_refused(registry, pointer):
    registry.add_pointer(
        RecordPointer(
            id="rec-2", abha_number=ABHA, care_context_id="cc-2",
            test_name="Chest X-ray", category="radiology",
            performed_on=date(2026, 3, 6), source_name="Tata Memorial Hospital",
            source_system=SourceSystem.ABDM, source_reference="tmh/dr/88299",
        )
    )
    request = _request(registry, categories=("molecular pathology",))
    registry.grant(
        request.id, granted_by="Shambhu Prasad",
        capacity=ConsentCapacity.SELF, channel=Channel.IVR,
    )
    outcome, _ = registry.resolve(
        "rec-2", requester_id=MUZAFFARPUR, purpose=ConsentPurpose.RECORD_MOVEMENT
    )
    assert outcome is AccessOutcome.OUT_OF_SCOPE


# ---------------------------------------------------------------- the audit


def test_refused_attempts_are_recorded_as_carefully_as_granted_ones(registry, pointer):
    """A log that only remembers what it allowed cannot tell you who tried."""
    registry.resolve(
        pointer.id, requester_id=MUZAFFARPUR, purpose=ConsentPurpose.RECORD_MOVEMENT
    )
    attempts = registry.access_log(ABHA)
    assert len(attempts) == 1
    assert attempts[0].allowed is False

    claims = [e.claim for e in registry.ledger.for_patient(ABHA)]
    assert any("access no consent" in c for c in claims)
    assert registry.ledger.verify() is True


def test_the_consent_history_survives_in_the_chain(registry, pointer):
    """What was consented to at a given moment has to outlive a screen."""
    request = _request(registry)
    grant = registry.grant(
        request.id, granted_by="Vikash",
        capacity=ConsentCapacity.NOMINEE, channel=Channel.IVR,
    )
    registry.revoke(grant.id, by="Shambhu Prasad", reason="moved back")

    claims = [e.claim for e in registry.ledger.for_patient(ABHA)]
    assert any("consent given" in c for c in claims)
    assert any("consent withdrawn" in c for c in claims)
    assert registry.ledger.verify() is True


def test_genomic_records_are_flagged_for_the_restricted_path():
    """Genomic data does not travel the general research route."""
    genomic = RecordPointer(
        id="g", abha_number=ABHA, care_context_id="cc", test_name="Somatic NGS panel",
        category="molecular pathology", performed_on=date(2026, 1, 1),
        source_name="Lab", source_system=SourceSystem.ABDM, source_reference="r",
    )
    plain = genomic.model_copy(update={"category": "radiology"})
    assert genomic.is_genomic is True
    assert plain.is_genomic is False


def test_notice_language_is_carried_on_the_grant(registry, pointer):
    """DPDP wants the notice in the patient's language; the grant proves it was."""
    request = _request(registry, notice_language=Language.HINDI)
    grant = registry.grant(
        request.id, granted_by="Shambhu Prasad",
        capacity=ConsentCapacity.SELF, channel=Channel.IVR,
    )
    assert grant.notice_language is Language.HINDI
    assert "in hi" in registry.ledger.for_patient(ABHA)[-1].claim


def test_a_grant_is_time_bounded_by_default():
    """A transfer for one episode of care is not an open-ended licence."""
    now = datetime.now(UTC)
    grant = ConsentGrant(
        id="g", request_id="r", abha_number=ABHA,
        purpose=ConsentPurpose.RECORD_MOVEMENT, requester_id=MUZAFFARPUR,
        requester_name="HBCH", categories=("radiology",), from_date=None, to_date=None,
        granted_at=now, expires_at=now + timedelta(days=90),
        granted_by="patient", capacity=ConsentCapacity.SELF,
        channel=Channel.IVR, notice_language=Language.HINDI,
    )
    assert grant.is_active(now) is True
    assert grant.is_active(now + timedelta(days=91)) is False
