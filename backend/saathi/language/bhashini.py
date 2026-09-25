"""Bhashini: speech and translation for Hindi, Bengali and Odia.

Saathi drafts in the family's language directly rather than drafting in English
and translating, because translation of a logistics instruction is exactly where
a date or a place name gets mangled. Bhashini is used for two things instead:

* TTS, to voice the message for families who cannot read.
* ASR, to hear a caregiver's spoken reply on an IVR call.

`translate` exists for the navigator console, so a coordinator who reads only
English can audit what was sent.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass

import httpx

from ..domain.enums import Language

logger = logging.getLogger(__name__)

PIPELINE_URL = "https://dhruva-api.bhashini.gov.in/services/inference/pipeline"

#: Bhashini uses ISO 639-1 codes that happen to match our Language values.
SUPPORTED = (Language.HINDI, Language.BENGALI, Language.ODIA)


@dataclass(frozen=True)
class Utterance:
    text: str
    language: Language
    #: WAV bytes when this came from or is destined for a voice channel.
    audio: bytes | None = None


class BhashiniUnavailable(RuntimeError):
    pass


class BhashiniClient:
    def __init__(self, api_key: str, user_id: str, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": api_key, "userID": user_id},
        )

    async def synthesise(self, text: str, language: Language) -> bytes:
        """Text to speech. Returns WAV bytes for the IVR leg."""
        if language not in SUPPORTED:
            raise BhashiniUnavailable(f"TTS unavailable for {language.value}")
        payload = {
            "pipelineTasks": [
                {
                    "taskType": "tts",
                    "config": {
                        "language": {"sourceLanguage": language.value},
                        "gender": "female",
                    },
                }
            ],
            "inputData": {"input": [{"source": text}]},
        }
        data = await self._post(payload)
        audio = data["pipelineResponse"][0]["audio"][0]["audioContent"]
        return base64.b64decode(audio)

    async def transcribe(self, audio: bytes, language: Language) -> str:
        """Speech to text for a caregiver's spoken reply."""
        if language not in SUPPORTED:
            raise BhashiniUnavailable(f"ASR unavailable for {language.value}")
        payload = {
            "pipelineTasks": [
                {
                    "taskType": "asr",
                    "config": {"language": {"sourceLanguage": language.value}},
                }
            ],
            "inputData": {
                "audio": [{"audioContent": base64.b64encode(audio).decode("ascii")}]
            },
        }
        data = await self._post(payload)
        return data["pipelineResponse"][0]["output"][0]["source"]

    async def translate(self, text: str, source: Language, target: Language) -> str:
        """For the navigator console's audit view only."""
        payload = {
            "pipelineTasks": [
                {
                    "taskType": "translation",
                    "config": {
                        "language": {
                            "sourceLanguage": source.value,
                            "targetLanguage": target.value,
                        }
                    },
                }
            ],
            "inputData": {"input": [{"source": text}]},
        }
        data = await self._post(payload)
        return data["pipelineResponse"][0]["output"][0]["target"]

    async def _post(self, payload: dict) -> dict:
        try:
            response = await self._client.post(PIPELINE_URL, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise BhashiniUnavailable(str(exc)) from exc

    async def aclose(self) -> None:
        await self._client.aclose()
