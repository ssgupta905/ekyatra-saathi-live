"""Delivery to a family, on whichever channel they use.

Delivery is the last mile and the one that fails silently. Every send returns a
`DeliveryReceipt` that the caller records, because "we sent it" and "they got
it" are different claims and only the second one keeps a family off a bus.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..domain.models import CaregiverMessage


@dataclass(frozen=True)
class DeliveryReceipt:
    channel: str
    accepted: bool
    provider_message_id: str | None
    sent_at: datetime
    error: str | None = None


class Transport(Protocol):
    async def send(self, message: CaregiverMessage, to: str) -> DeliveryReceipt: ...
