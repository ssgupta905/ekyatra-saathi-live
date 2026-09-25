"""Exotel IVR voice calls.

Voice is not a fallback here — for a large share of caregivers it is the only
channel that works. The message is synthesised by Bhashini and played back; the
caregiver's spoken reply is transcribed and screened by the clinical guard
before anything is done with it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from ..domain.enums import Language
from ..domain.models import CaregiverMessage
from ..language import guard
from ..language.bhashini import BhashiniClient, BhashiniUnavailable
from .whatsapp import DeliveryReceipt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CallReply:
    """What the caregiver said back, after screening."""

    patient_id: str
    transcript: str
    language: Language
    #: False when the reply asked something clinical and was routed to a human.
    answerable: bool
    routing_reason: str | None = None


class ExotelTransport:
    def __init__(
        self,
        sid: str,
        token: str,
        caller_id: str,
        bhashini: BhashiniClient,
        timeout: float = 30.0,
    ) -> None:
        self._sid = sid
        self._caller_id = caller_id
        self._bhashini = bhashini
        self._client = httpx.AsyncClient(
            base_url=f"https://api.exotel.com/v1/Accounts/{sid}",
            auth=(sid, token),
            timeout=timeout,
        )

    async def send(self, message: CaregiverMessage, to: str) -> DeliveryReceipt:
        now = datetime.now(UTC)
        if message.routed_to_care_team:
            return DeliveryReceipt("ivr", False, None, now, message.routing_reason)
        try:
            await self._bhashini.synthesise(message.body, message.language)
        except BhashiniUnavailable as exc:
            logger.error("tts failed for %s: %s", message.patient_id, exc)
            return DeliveryReceipt("ivr", False, None, now, f"tts failed: {exc}")

        try:
            response = await self._client.post(
                "/Calls/connect.json",
                data={"From": self._caller_id, "To": to, "CallerId": self._caller_id},
            )
            response.raise_for_status()
            call_sid = response.json().get("Call", {}).get("Sid")
            return DeliveryReceipt("ivr", True, call_sid, now)
        except httpx.HTTPError as exc:
            logger.error("ivr call failed for %s: %s", message.patient_id, exc)
            return DeliveryReceipt("ivr", False, None, now, str(exc))

    async def receive_reply(
        self, patient_id: str, audio: bytes, language: Language
    ) -> CallReply:
        """Transcribe and screen a spoken reply."""
        transcript = await self._bhashini.transcribe(audio, language)
        verdict = guard.screen_inbound(transcript)
        return CallReply(
            patient_id=patient_id,
            transcript=transcript,
            language=language,
            answerable=verdict.allowed,
            routing_reason=verdict.reason,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
