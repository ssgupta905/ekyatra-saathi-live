"""Turning what other parties say into `ReadinessItem`s.

Pure functions: no network, no clock. The callers that talk to a hospital desk,
a scheme endpoint or a partner pass in what they heard, and these decide how to
read it. The one rule they share is the one `tools/schemes.py` states: nobody
having told us is not the same as "no", and it is never read as "yes".
"""

from __future__ import annotations

from datetime import date

from ..domain.enums import ReadinessKind, ReadinessStatus, SourceSystem
from ..domain.models import ReadinessItem


def slot_item(
    *,
    patient_id: str,
    step_id: str,
    party: str,
    resource_up: bool | None,
    next_free: date | None = None,
    alternative: bool = False,
    source: SourceSystem = SourceSystem.HOSPITAL_FEED,
) -> ReadinessItem:
    """A booked slot: ready when its resource is up, blocked when it is down.

    `resource_up=None` means nobody has said, which is unknown rather than up.
    """
    if resource_up is None:
        status = ReadinessStatus.UNKNOWN
    elif resource_up:
        status = ReadinessStatus.READY
    else:
        status = ReadinessStatus.BLOCKED
    return ReadinessItem(
        id=f"{step_id}-slot",
        patient_id=patient_id,
        step_id=step_id,
        kind=ReadinessKind.SLOT,
        party=party,
        status=status,
        ready_by=next_free if status is ReadinessStatus.BLOCKED else None,
        alternative_available=alternative,
        source=source,
    )


def insurance_item(
    *,
    patient_id: str,
    party: str,
    approved: bool | None,
    step_id: str | None = None,
    pending: bool = False,
    alternative: bool = False,
    source: SourceSystem = SourceSystem.PARTNER,
) -> ReadinessItem:
    """Pre-authorisation: approved, refused, in progress, or nobody has asked."""
    if approved is True:
        status = ReadinessStatus.READY
    elif approved is False:
        status = ReadinessStatus.BLOCKED
    elif pending:
        status = ReadinessStatus.PENDING
    else:
        status = ReadinessStatus.UNKNOWN
    return ReadinessItem(
        id=f"{step_id or patient_id}-insurance",
        patient_id=patient_id,
        step_id=step_id,
        kind=ReadinessKind.INSURANCE,
        party=party,
        status=status,
        alternative_available=alternative,
        source=source,
    )
