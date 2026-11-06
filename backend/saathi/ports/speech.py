"""Turning a family's voice into words, and words back into a voice.

Two capabilities, kept apart because they fail apart and because a deployment
may reasonably have one and not the other.

Speech is not a convenience in this product. A caregiver who cannot read their
own script has no other way in, and the languages this serves are exactly the
ones general-purpose providers serve worst: there is no browser voice for Odia
at all. So the port exists to let an Indian-language provider be the one that
does this work, with a general one behind it rather than in front.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Transcript:
    """What was heard. Words only — acting on them is somebody else's job."""

    text: str
    language: str
    #: Which service and model produced it, for the audit trail and the screen.
    heard_by: str


@dataclass(frozen=True)
class Utterance:
    """Audio to play back, and what it says."""

    audio: bytes
    media_type: str
    language: str
    spoken_by: str


class SpeechToText(Protocol):
    def transcribe(self, audio: bytes, filename: str, language: str) -> Transcript | None:
        """Words from a recording, or None when this service could not help.

        None rather than an exception: a transcription that silently returned
        nothing would read as "the family said nothing", which is a different
        and much worse claim than "we could not hear it".
        """
        ...

    def describe(self) -> str: ...


class TextToSpeech(Protocol):
    def say(self, text: str, language: str) -> Utterance | None:
        """Audio for text already written and already checked.

        Never given anything the guard has not passed: this reads out a message,
        it does not compose one.
        """
        ...

    def describe(self) -> str: ...


__all__ = ["SpeechToText", "TextToSpeech", "Transcript", "Utterance"]
