"""Sarvam: speech in the languages this product is actually for.

Chosen for one reason that is not marketing. The families here read Hindi,
Bengali and Odia, and **no browser ships an Odia voice** — the read-aloud
button on the family's phone did nothing at all for an Odia family, silently,
which is the worst way for an accessibility feature to fail. Sarvam speaks all
three, and hears Indian-accented speech in them.

Two models, both named by the service rather than guessed at: `bulbul:v3` for
speech and `saarika:v2.5` for listening. Both earlier versions answer a request
with a deprecation notice rather than audio, so the names are pinned here and
in configuration, not inferred.

Failure is always `None`. A caller that gets nothing falls back to whatever
else is configured, and a family hears a general-purpose voice instead of a
good one — which is worse than the alternative but far better than silence.
"""

from __future__ import annotations

import base64
import logging

import httpx

from ...ports.speech import Transcript, Utterance

logger = logging.getLogger(__name__)

BASE_URL = "https://api.sarvam.ai"

#: Sarvam's own language codes. Odia is `od-IN`, not the `or` of ISO 639-1 that
#: the rest of this codebase uses, and sending the wrong one is a 400.
LANGUAGE_CODES = {
    "hi": "hi-IN",
    "bn": "bn-IN",
    "or": "od-IN",
    "en": "en-IN",
}


class SarvamSpeech:
    """Listening and speaking, for one API key."""

    def __init__(
        self,
        api_key: str,
        *,
        listen_model: str = "saarika:v2.5",
        speak_model: str = "bulbul:v3",
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._key = api_key
        self._listen_model = listen_model
        self._speak_model = speak_model
        self._timeout = timeout
        self._client = client

    # ---------------- plumbing ----------------

    def _post(self, path: str, **kwargs) -> dict | None:
        headers = {"api-subscription-key": self._key, **kwargs.pop("headers", {})}
        try:
            if self._client is not None:
                response = self._client.post(
                    f"{BASE_URL}{path}", headers=headers, timeout=self._timeout, **kwargs
                )
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(f"{BASE_URL}{path}", headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            logger.warning("sarvam %s unreachable: %s", path, exc)
            return None
        if response.status_code >= 400:
            # The service says *why* — a deprecated model name, a bad language
            # code — and that sentence is worth far more in a log than a 400.
            logger.warning("sarvam %s refused: %s %s", path, response.status_code,
                           response.text[:200])  # fmt: skip
            return None
        try:
            return response.json()
        except ValueError:
            logger.warning("sarvam %s did not return json", path)
            return None

    def describe(self) -> str:
        return f"Sarvam · {self._listen_model} / {self._speak_model}"

    # ---------------- listening ----------------

    def transcribe(self, audio: bytes, filename: str, language: str) -> Transcript | None:
        code = LANGUAGE_CODES.get(language)
        if code is None:
            logger.info("sarvam does not cover %s; leaving it to the fallback", language)
            return None
        body = self._post(
            "/speech-to-text",
            files={"file": (filename or "reply.wav", audio, "audio/wav")},
            data={"model": self._listen_model, "language_code": code},
        )
        if body is None:
            return None
        text = str(body.get("transcript") or "").strip()
        if not text:
            # Heard nothing is not the same as said nothing; let the caller
            # decide rather than handing back an empty transcript as a fact.
            return None
        return Transcript(text=text, language=language, heard_by=f"Sarvam · {self._listen_model}")

    # ---------------- speaking ----------------

    def say(self, text: str, language: str) -> Utterance | None:
        code = LANGUAGE_CODES.get(language)
        if code is None or not text.strip():
            return None
        body = self._post(
            "/text-to-speech",
            headers={"Content-Type": "application/json"},
            json={
                "text": text,
                "target_language_code": code,
                "model": self._speak_model,
            },
        )
        if body is None:
            return None
        audios = body.get("audios") or []
        if not audios:
            return None
        try:
            audio = base64.b64decode(audios[0])
        except (ValueError, TypeError):
            logger.warning("sarvam returned audio that is not base64")
            return None
        return Utterance(
            audio=audio,
            media_type="audio/wav",
            language=language,
            spoken_by=f"Sarvam · {self._speak_model}",
        )


__all__ = ["SarvamSpeech"]
