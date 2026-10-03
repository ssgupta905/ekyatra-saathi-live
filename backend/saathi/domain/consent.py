"""Consent, and the records it gates.

Saathi holds a **consented index, never the records**. The distinction is the
whole feature: a `RecordPointer` says *that* a BRCA1 panel was done at Tata
Memorial on 4 March and where the original lives. It has no field that can hold
what the report said, in the same way `domain/models.py` has none — and
`ingest/abdm.py` already drops `conclusion`, `presentedForm` and `result` before
anything downstream sees a FHIR resource. That is a property of the type, not a
discipline somebody has to remember.

Three things in here are easy to get wrong and are worth stating plainly.

**The metadata is itself clinical.** "BRCA1 germline panel" tells a reader that
somebody suspected a hereditary cancer syndrome. Navigators in this system are
explicitly not clinical staff, so they see `category` — "molecular pathology" —
and the patient and the care team see the full name. Redacting the index is not
paranoia; a timeline is a diagnosis if you read it sideways.

**Consent belongs to the patient.** Under the DPDP Act a family member acts only
as a nominee the patient named, or as the verified guardian of a child. Vikash
handling everything for Shambhu is the nominee case and is recorded as one.
`capacity` is never assumed from the fact that somebody answered the phone.

**Revocation stops future sharing and nothing else.** A centre that lawfully
received a record keeps it under its own retention duties. Any interface
implying "withdraw and it is gone" promises what no system can deliver, so the
model says `revoked_at` and the copy says "no further access", not "erased".

Saathi is a consent *requester*. It is deliberately not a consent manager — that
regime begins 13 November 2026 and registering for it is a regulatory lift this
project has no reason to take on.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from pydantic import Field

from .enums import Channel, Language, SourceSystem
from .models import Base


class ConsentPurpose(StrEnum):
    """Why access is being asked for. Never bundled; each is asked separately."""

    #: What Saathi does today: coordinate visits from status alone.
    CARE_COORDINATION = "care_coordination"
    #: A new centre needs this patient's existing records to take over care.
    RECORD_MOVEMENT = "record_movement"
    #: Optional, and never a condition of care.
    RESEARCH = "research"


class ConsentCapacity(StrEnum):
    """In what standing the person consenting is entitled to do so."""

    SELF = "self"
    #: Named by the patient. Not "a relative who answered".
    NOMINEE = "nominee"
    #: Verified guardian of a minor.
    GUARDIAN = "guardian"


class AccessOutcome(StrEnum):
    GRANTED = "granted"
    #: No grant covers this request.
    NO_CONSENT = "no_consent"
    #: There was one, and it was withdrawn.
    REVOKED = "revoked"
    EXPIRED = "expired"
    #: Out of the categories or the date window the patient agreed to.
    OUT_OF_SCOPE = "out_of_scope"


#: Research on genomic data does not travel this path. Genomic data cannot be
#: meaningfully anonymised, and sharing runs through the Indian Biological Data
#: Centre under the Department of Biotechnology's rules, to ethics-approved
#: studies, under a code rather than a name. Saathi never transfers it directly
#: and never abroad — cross-border transfer is restrictable by government order.
GENOMIC_CATEGORIES: frozenset[str] = frozenset(
    {"genomic", "molecular pathology", "germline panel", "somatic panel"}
)

#: Default life of a record-movement grant. A transfer to one centre for one
#: episode of care is not an open-ended licence, and purpose limitation is an
#: obligation rather than a nicety.
DEFAULT_GRANT_DAYS = 90


class RecordPointer(Base):
    """Where a report lives. Not the report.

    Every field here is metadata about the existence of a document. There is
    deliberately no `value`, no `conclusion`, no `text` and no `attachment`, and
    `tests/test_consent.py` asserts there never is.
    """

    id: str
    #: ABDM identity. The patient's own id, not one Saathi invented.
    abha_number: str
    #: The ABDM care context this record hangs off at its source.
    care_context_id: str
    #: Full name of the test. Shown to the patient and the care team.
    test_name: str
    #: Coarse grouping shown to non-clinical staff — see the module docstring.
    category: str
    performed_on: date
    #: Who holds the original.
    source_name: str
    source_system: SourceSystem
    #: Opaque handle at the source. Resolving it is the source's job, under a
    #: live consent. It is not a copy and it is not a URL to content Saathi has.
    source_reference: str
    #: True when the family uploaded the original to their own ABHA health
    #: locker because the lab is not linked to ABDM. The locker stays the source
    #: of truth; Saathi still only points at it.
    in_health_locker: bool = False

    @property
    def is_genomic(self) -> bool:
        return self.category.lower() in GENOMIC_CATEGORIES

    def as_seen_by(self, role: str) -> dict:
        """What this row looks like to a given role.

        A navigator coordinating journeys has no clinical reason to know which
        panel was run, and the test name would tell them. They get the category.
        """
        shared = {
            "id": self.id,
            "category": self.category,
            "performed_on": self.performed_on.isoformat(),
            "source_name": self.source_name,
            "in_health_locker": self.in_health_locker,
        }
        if role in ("patient", "caregiver", "doctor", "admin"):
            return {**shared, "test_name": self.test_name}
        return {**shared, "test_name": None, "redacted": True}


class ConsentRequest(Base):
    """An ask, before anyone has answered it."""

    id: str
    abha_number: str
    purpose: ConsentPurpose
    requester_id: str
    requester_name: str
    #: Categories asked for. Never "everything" — purpose limitation means the
    #: ask is as narrow as the reason for it.
    categories: tuple[str, ...]
    from_date: date | None = None
    to_date: date | None = None
    reason: str = ""
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    #: The language the notice must be given in. DPDP requires the data
    #: principal's own language, which for this pilot means the voice line.
    notice_language: Language = Language.HINDI


class ConsentGrant(Base):
    """A patient's answer, with everything needed to defend it later."""

    id: str
    request_id: str
    abha_number: str
    purpose: ConsentPurpose
    requester_id: str
    requester_name: str
    categories: tuple[str, ...]
    from_date: date | None
    to_date: date | None
    granted_at: datetime
    expires_at: datetime
    #: Who pressed 1, and in what standing.
    granted_by: str
    capacity: ConsentCapacity
    #: How the notice was given and the answer taken.
    channel: Channel
    notice_language: Language
    revoked_at: datetime | None = None
    revocation_reason: str | None = None

    def is_active(self, at: datetime | None = None) -> bool:
        at = at or datetime.now(UTC)
        if self.revoked_at is not None and at >= self.revoked_at:
            return False
        return at < self.expires_at

    def covers(self, pointer: RecordPointer, at: datetime | None = None) -> bool:
        """Whether this grant actually permits this record, right now."""
        if not self.is_active(at):
            return False
        if self.abha_number != pointer.abha_number:
            return False
        if self.categories and pointer.category not in self.categories:
            return False
        if self.from_date and pointer.performed_on < self.from_date:
            return False
        if self.to_date and pointer.performed_on > self.to_date:
            return False
        return True

    def why_not(self, pointer: RecordPointer, at: datetime | None = None) -> AccessOutcome:
        """The specific reason this grant does not cover a record.

        Separate from `covers` because an audit needs to distinguish "withdrawn"
        from "never asked for" — they are different failures with different
        obligations attached.
        """
        at = at or datetime.now(UTC)
        if self.revoked_at is not None and at >= self.revoked_at:
            return AccessOutcome.REVOKED
        if at >= self.expires_at:
            return AccessOutcome.EXPIRED
        if self.covers(pointer, at):
            return AccessOutcome.GRANTED
        return AccessOutcome.OUT_OF_SCOPE


class AccessAttempt(Base):
    """Every resolution, allowed or refused. The refusals matter most."""

    id: str
    abha_number: str
    pointer_id: str
    requester_id: str
    purpose: ConsentPurpose
    outcome: AccessOutcome
    at: datetime
    grant_id: str | None = None

    @property
    def allowed(self) -> bool:
        return self.outcome is AccessOutcome.GRANTED


def default_expiry(granted_at: datetime, days: int = DEFAULT_GRANT_DAYS) -> datetime:
    return granted_at + timedelta(days=days)
