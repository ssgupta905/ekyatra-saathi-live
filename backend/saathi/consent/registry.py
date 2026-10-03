"""The consent registry: ask, answer, withdraw, and check at every read.

Three properties this has that a consent flag on a row does not.

**Every event is a ledger row.** Grants, withdrawals and access attempts go into
the same hash-chained ledger as everything else, so "what was this patient
consented to at 14:02 on 3 March" has an answer that survives somebody editing a
database. An auditor asking that question is the whole reason the ledger exists.

**Enforcement happens at read.** `resolve` checks the live grant every time a
pointer is opened, not once when it was issued. A withdrawal that only changes a
flag on a screen is not a withdrawal; this one makes the record stop resolving
within the same call.

**Refusals are recorded too.** An attempt that fails writes an `AccessAttempt`
exactly as a success does. A system that logs only what it allowed cannot tell
you whether anyone has been trying the door.

Saathi is the requester here, never the consent manager. It asks; the patient
answers on their own phone, in their own language; the source holds the record
and does its own check at its end.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from ..domain.consent import (
    AccessAttempt,
    AccessOutcome,
    ConsentCapacity,
    ConsentGrant,
    ConsentPurpose,
    ConsentRequest,
    RecordPointer,
    default_expiry,
)
from ..domain.enums import Channel, Language, SourceSystem
from ..ledger.evidence import InMemoryEvidenceLedger

logger = logging.getLogger(__name__)


class ConsentError(RuntimeError):
    """Raised when an operation is not permitted, rather than silently ignored."""


@dataclass
class ConsentRegistry:
    """Consent records for every patient, backed by the evidence ledger."""

    ledger: InMemoryEvidenceLedger
    requests: dict[str, ConsentRequest] = field(default_factory=dict)
    grants: dict[str, ConsentGrant] = field(default_factory=dict)
    pointers: dict[str, RecordPointer] = field(default_factory=dict)
    attempts: list[AccessAttempt] = field(default_factory=list)

    # ---------------- the index ----------------

    def add_pointer(self, pointer: RecordPointer) -> RecordPointer:
        """Index that a record exists. Never its contents."""
        self.pointers[pointer.id] = pointer
        self.ledger.record_once(
            patient_id=pointer.abha_number,
            source=pointer.source_system,
            source_record_id=pointer.source_reference,
            claim=(
                f"{pointer.category} record from {pointer.source_name}, "
                f"{pointer.performed_on.isoformat()}"
            ),
            metadata={"pointer_id": pointer.id, "care_context": pointer.care_context_id},
        )
        return pointer

    def timeline(self, abha_number: str, *, role: str) -> list[dict]:
        """This patient's records, redacted for who is looking."""
        rows = [p for p in self.pointers.values() if p.abha_number == abha_number]
        rows.sort(key=lambda p: p.performed_on, reverse=True)
        return [p.as_seen_by(role) for p in rows]

    # ---------------- asking ----------------

    def request(
        self,
        *,
        abha_number: str,
        purpose: ConsentPurpose,
        requester_id: str,
        requester_name: str,
        categories: tuple[str, ...],
        reason: str = "",
        from_date: date | None = None,
        to_date: date | None = None,
        notice_language: Language = Language.HINDI,
    ) -> ConsentRequest:
        """Raise an ask. Nothing is accessible until it is answered.

        `categories` is required and must be specific. An empty ask would mean
        "everything", which is the opposite of purpose limitation.
        """
        if not categories:
            raise ConsentError(
                "a consent request must name the categories it needs; "
                "'everything' is not a purpose"
            )
        request = ConsentRequest(
            id=str(uuid.uuid4()),
            abha_number=abha_number,
            purpose=purpose,
            requester_id=requester_id,
            requester_name=requester_name,
            categories=categories,
            from_date=from_date,
            to_date=to_date,
            reason=reason,
            notice_language=notice_language,
        )
        self.requests[request.id] = request
        return request

    def pending(self, abha_number: str) -> list[ConsentRequest]:
        answered = {g.request_id for g in self.grants.values()}
        return [
            r
            for r in self.requests.values()
            if r.abha_number == abha_number and r.id not in answered
        ]

    # ---------------- answering ----------------

    def grant(
        self,
        request_id: str,
        *,
        granted_by: str,
        capacity: ConsentCapacity,
        channel: Channel,
        days: int | None = None,
    ) -> ConsentGrant:
        """Record a patient's yes, with how it was given and by whom.

        `capacity` is never inferred. Somebody answering the patient's phone is
        not thereby their nominee, and the difference is the whole of the DPDP
        position on who may consent.
        """
        request = self.requests.get(request_id)
        if request is None:
            raise ConsentError(f"unknown consent request {request_id}")

        granted_at = datetime.now(UTC)
        grant = ConsentGrant(
            id=str(uuid.uuid4()),
            request_id=request.id,
            abha_number=request.abha_number,
            purpose=request.purpose,
            requester_id=request.requester_id,
            requester_name=request.requester_name,
            categories=request.categories,
            from_date=request.from_date,
            to_date=request.to_date,
            granted_at=granted_at,
            expires_at=default_expiry(granted_at, days) if days else default_expiry(granted_at),
            granted_by=granted_by,
            capacity=capacity,
            channel=channel,
            notice_language=request.notice_language,
        )
        self.grants[grant.id] = grant
        self.ledger.record(
            patient_id=grant.abha_number,
            source=SourceSystem.CAREGIVER_REPLY,
            source_record_id=grant.id,
            claim=(
                f"consent given for {grant.purpose.value.replace('_', ' ')} to "
                f"{grant.requester_name}, by {granted_by} as {capacity.value}, "
                f"on {channel.value} in {grant.notice_language.value}"
            ),
            metadata={
                "categories": list(grant.categories),
                "expires_at": grant.expires_at.isoformat(),
                "request_id": grant.request_id,
            },
        )
        return grant

    def revoke(self, grant_id: str, *, by: str, reason: str = "") -> ConsentGrant:
        """Withdraw a grant. Stops future access; undoes nothing already shared."""
        grant = self.grants.get(grant_id)
        if grant is None:
            raise ConsentError(f"unknown grant {grant_id}")
        if grant.revoked_at is not None:
            return grant

        revoked = grant.model_copy(
            update={"revoked_at": datetime.now(UTC), "revocation_reason": reason}
        )
        self.grants[grant_id] = revoked
        self.ledger.record(
            patient_id=revoked.abha_number,
            source=SourceSystem.CAREGIVER_REPLY,
            source_record_id=revoked.id,
            claim=(
                f"consent withdrawn for {revoked.purpose.value.replace('_', ' ')} "
                f"from {revoked.requester_name}, by {by}"
                + (f": {reason}" if reason else "")
            ),
            metadata={"withdrawn": True},
        )
        return revoked

    def active_grants(
        self, abha_number: str, purpose: ConsentPurpose | None = None
    ) -> list[ConsentGrant]:
        return [
            g
            for g in self.grants.values()
            if g.abha_number == abha_number
            and g.is_active()
            and (purpose is None or g.purpose is purpose)
        ]

    # ---------------- reading ----------------

    def resolve(
        self,
        pointer_id: str,
        *,
        requester_id: str,
        purpose: ConsentPurpose,
        at: datetime | None = None,
    ) -> tuple[AccessOutcome, RecordPointer | None]:
        """Check live consent and return the pointer, or refuse and say why.

        Returns the *pointer*, never content — resolving the reference against
        the source is the source's job, under its own check. What this decides
        is whether Saathi will even hand over the handle.
        """
        at = at or datetime.now(UTC)
        pointer = self.pointers.get(pointer_id)
        if pointer is None:
            raise ConsentError(f"unknown record pointer {pointer_id}")

        candidates = [
            g
            for g in self.grants.values()
            if g.abha_number == pointer.abha_number
            and g.purpose is purpose
            and g.requester_id == requester_id
        ]

        outcome = AccessOutcome.NO_CONSENT
        matched: ConsentGrant | None = None
        for grant in candidates:
            verdict = grant.why_not(pointer, at)
            if verdict is AccessOutcome.GRANTED:
                outcome, matched = verdict, grant
                break
            # Keep the most informative refusal: "you had consent and withdrew
            # it" is a different fact from "you never asked".
            if outcome is AccessOutcome.NO_CONSENT:
                outcome, matched = verdict, grant

        self._log_attempt(pointer, requester_id, purpose, outcome, matched, at)
        return (outcome, pointer if outcome is AccessOutcome.GRANTED else None)

    def _log_attempt(
        self,
        pointer: RecordPointer,
        requester_id: str,
        purpose: ConsentPurpose,
        outcome: AccessOutcome,
        grant: ConsentGrant | None,
        at: datetime,
    ) -> None:
        attempt = AccessAttempt(
            id=str(uuid.uuid4()),
            abha_number=pointer.abha_number,
            pointer_id=pointer.id,
            requester_id=requester_id,
            purpose=purpose,
            outcome=outcome,
            at=at,
            grant_id=grant.id if grant else None,
        )
        self.attempts.append(attempt)
        # Refused attempts are recorded as deliberately as granted ones. A log
        # that only remembers what it allowed cannot answer whether somebody has
        # been trying the door.
        self.ledger.record(
            patient_id=pointer.abha_number,
            source=SourceSystem.DERIVED,
            source_record_id=attempt.id,
            claim=(
                f"record access {outcome.value.replace('_', ' ')} for "
                f"{requester_id} ({purpose.value.replace('_', ' ')}), "
                f"{pointer.category} from {pointer.source_name}"
            ),
            metadata={"pointer_id": pointer.id, "grant_id": attempt.grant_id},
        )

    def access_log(self, abha_number: str) -> list[AccessAttempt]:
        return [a for a in self.attempts if a.abha_number == abha_number]

    def snapshot(self, abha_number: str) -> dict:
        grants = [g for g in self.grants.values() if g.abha_number == abha_number]
        return {
            "records": len([p for p in self.pointers.values() if p.abha_number == abha_number]),
            "grants": [
                {
                    "id": g.id,
                    "purpose": g.purpose.value,
                    "requester": g.requester_name,
                    "categories": list(g.categories),
                    "granted_by": g.granted_by,
                    "capacity": g.capacity.value,
                    "channel": g.channel.value,
                    "language": g.notice_language.value,
                    "expires_at": g.expires_at.isoformat(),
                    "active": g.is_active(),
                    "revoked_at": g.revoked_at.isoformat() if g.revoked_at else None,
                }
                for g in sorted(grants, key=lambda g: g.granted_at, reverse=True)
            ],
            "pending": [
                {
                    "id": r.id,
                    "purpose": r.purpose.value,
                    "requester": r.requester_name,
                    "categories": list(r.categories),
                    "reason": r.reason,
                    "language": r.notice_language.value,
                }
                for r in self.pending(abha_number)
            ],
            "attempts": len(self.access_log(abha_number)),
            "refused": len([a for a in self.access_log(abha_number) if not a.allowed]),
        }
