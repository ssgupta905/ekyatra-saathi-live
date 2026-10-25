"""WhatsApp Business API delivery.

Implements the `Transport` port (`ports/transport.py`). Every send returns a
`DeliveryReceipt` that the caller records.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from ..domain.models import CaregiverMessage
from ..ports.transport import DeliveryReceipt

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v21.0"


class WhatsAppTransport:
    def __init__(self, phone_number_id: str, token: str, timeout: float = 20.0) -> None:
        self._phone_number_id = phone_number_id
        self._client = httpx.AsyncClient(
            base_url=GRAPH_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    async def send(self, message: CaregiverMessage, to: str) -> DeliveryReceipt:
        now = datetime.now(UTC)
        if message.routed_to_care_team:
            # Never send a diverted message to the family.
            return DeliveryReceipt(
                "whatsapp", False, None, now, message.routing_reason or "diverted"
            )
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message.body, "preview_url": False},
        }
        try:
            response = await self._client.post(
                f"/{self._phone_number_id}/messages", json=payload
            )
            response.raise_for_status()
            data = response.json()
            message_id = data.get("messages", [{}])[0].get("id")
            return DeliveryReceipt("whatsapp", True, message_id, now)
        except httpx.HTTPError as exc:
            logger.error("whatsapp send failed for %s: %s", message.patient_id, exc)
            return DeliveryReceipt("whatsapp", False, None, now, str(exc))

    async def aclose(self) -> None:
        await self._client.aclose()


class ConsoleTransport:
    """Prints instead of sending. Default in local and CI runs."""

    def __init__(self) -> None:
        self.sent: list[CaregiverMessage] = []

    async def send(self, message: CaregiverMessage, to: str = "") -> DeliveryReceipt:
        now = datetime.now(UTC)
        if message.routed_to_care_team:
            return DeliveryReceipt("console", False, None, now, message.routing_reason)
        self.sent.append(message)
        print(f"[{message.channel.value}:{message.language.value} -> {to}] {message.body}")
        return DeliveryReceipt("console", True, f"local-{len(self.sent)}", now)
