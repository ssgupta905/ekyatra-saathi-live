"""The Sarvam adapter: what it sends, and how it fails.

Chosen for one reason that is not marketing — no browser ships an Odia voice,
so for an Odia family the read-aloud button was a control that did nothing.
These tests pin the two things that would silently undo that: the language code
Sarvam actually wants, and failing to `None` rather than to an empty transcript
that reads as "the family said nothing".

No network. The HTTP client is a stand-in.
"""

from __future__ import annotations

import base64

import httpx
import pytest
from saathi.adapters.speech.sarvam import LANGUAGE_CODES, SarvamSpeech


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_odia_is_sent_as_od_not_or():
    """ISO 639-1 says `or`; Sarvam wants `od-IN`, and the wrong one is a 400.

    This is the whole reason the adapter exists for Odia families, so it is the
    thing most worth pinning.
    """
    assert LANGUAGE_CODES["or"] == "od-IN"
    assert LANGUAGE_CODES["hi"] == "hi-IN"
    assert LANGUAGE_CODES["bn"] == "bn-IN"


def test_speaking_asks_for_the_right_language_and_returns_audio():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.update(json.loads(request.content), path=request.url.path)
        seen["key"] = request.headers.get("api-subscription-key")
        return httpx.Response(
            200, json={"audios": [base64.b64encode(b"RIFFfake").decode()]}
        )

    spoken = SarvamSpeech("k", client=_client(handler)).say("ଆସନ୍ତୁ", "or")

    assert spoken is not None
    assert spoken.audio == b"RIFFfake"
    assert spoken.media_type == "audio/wav"
    assert seen["target_language_code"] == "od-IN"
    assert seen["path"] == "/text-to-speech"
    assert seen["key"] == "k"


def test_listening_returns_the_transcript_and_who_heard_it():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"transcript": "  दवा का क्या होगा  "})

    heard = SarvamSpeech("k", client=_client(handler)).transcribe(b"...", "a.wav", "hi")

    assert heard is not None
    assert heard.text == "दवा का क्या होगा", "whitespace should not reach the family's screen"
    assert "saarika" in heard.heard_by


def test_a_refusal_is_none_so_the_next_service_is_tried():
    """A deprecated model name answers 400 with a sentence saying so.

    That is exactly how this was found: `bulbul:v2` returns a deprecation
    notice rather than audio. Returning None lets the fallback run instead of
    raising through the endpoint.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "Model deprecated"}})

    speech = SarvamSpeech("k", client=_client(handler))

    assert speech.say("कुछ", "hi") is None
    assert speech.transcribe(b"...", "a.wav", "hi") is None


def test_an_empty_transcript_is_none_not_silence():
    """Heard nothing and said nothing are different claims."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"transcript": "   "})

    assert SarvamSpeech("k", client=_client(handler)).transcribe(b"x", "a.wav", "hi") is None


def test_a_language_sarvam_does_not_cover_is_left_to_someone_else():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    speech = SarvamSpeech("k", client=_client(handler))

    assert speech.transcribe(b"x", "a.wav", "ta") is None
    assert speech.say("something", "ta") is None
    assert not called, "an unsupported language should not cost a request"


@pytest.mark.parametrize("fault", [httpx.ConnectError, httpx.ReadTimeout])
def test_a_network_fault_is_none_rather_than_an_exception(fault):
    def handler(request: httpx.Request) -> httpx.Response:
        raise fault("down")

    speech = SarvamSpeech("k", client=_client(handler))

    assert speech.say("कुछ", "hi") is None
    assert speech.transcribe(b"x", "a.wav", "hi") is None
