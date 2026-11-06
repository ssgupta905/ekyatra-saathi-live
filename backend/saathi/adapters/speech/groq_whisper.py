"""Whisper, behind the same port — the fallback, not the first choice.

It hears Hindi and Bengali well enough. It is second to Sarvam here because
these are Indian-language families with Indian accents, and because it cannot
speak at all: there is no counterpart for reading a message out, so a
deployment with only this one has a mute family app.
"""

from __future__ import annotations

import logging

import groq

from ...ports.speech import Transcript

logger = logging.getLogger(__name__)


class GroqWhisper:
    def __init__(self, api_key: str, model: str = "whisper-large-v3-turbo") -> None:
        self._key = api_key
        self._model = model

    def describe(self) -> str:
        return f"Groq · {self._model}"

    def transcribe(self, audio: bytes, filename: str, language: str) -> Transcript | None:
        client = groq.Groq(api_key=self._key)
        try:
            result = client.audio.transcriptions.create(
                file=(filename or "reply.webm", audio),
                model=self._model,
                language=language,
                temperature=0.0,
            )
        except groq.APIError as exc:
            logger.warning("whisper could not transcribe: %s", exc)
            return None
        text = (getattr(result, "text", "") or "").strip()
        if not text:
            return None
        return Transcript(text=text, language=language, heard_by=self.describe())


__all__ = ["GroqWhisper"]
