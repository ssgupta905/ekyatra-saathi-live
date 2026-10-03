"""The family's own surface: what they were told, and what they can say back.

A caregiver holding a feature phone in Gaya is not a user of a hospital system.
They get one plan, in their language, and a way to ask about it. Everything here
is shaped by that: no ids, no statuses, no jargon, and nothing that assumes a
screen is being looked at rather than a phone being listened to.

Two endpoints do the work. `/notifications` is the family's own record of what
reached them — holding messages, plan messages, and what they said back, in the
order it happened. `/voice/transcribe` turns a spoken reply into text through
Groq's multilingual Whisper, because for a large share of these families voice
is not a convenience, it is the only channel that works.

The guard sits where it always does. A transcript is an inbound message like any
other: `screen_inbound` reads it, a clinical question is logged and routed to a
person, and nothing here answers one.
"""

from __future__ import annotations

import logging
from typing import Annotated

import groq
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..domain.enums import Language

logger = logging.getLogger(__name__)

router = APIRouter()

#: Groq's multilingual speech-to-text. The turbo model is the cheaper and faster
#: of the two and is comfortably good enough for a short spoken reply.
WHISPER_MODEL = "whisper-large-v3-turbo"

#: Whisper bills a minimum of ten seconds and accepts very short clips; anything
#: under this is almost certainly a mis-tap rather than speech.
MIN_AUDIO_BYTES = 1_200

#: Well under Groq's limit. A caregiver's reply is seconds long; a file this big
#: is a mistake worth refusing early rather than paying to transcribe.
MAX_AUDIO_BYTES = 8 * 1024 * 1024


def _state(request: Request):
    return request.app.state.saathi


@router.get("/patients/{patient_id}/notifications")
async def notifications(request: Request, patient_id: str, limit: int = 30) -> dict:
    """What this family was told, and what they said, newest last.

    One merged thread rather than two lists: a family does not experience "the
    hospital's outbound queue" and "my replies" as separate things, and reading
    the holding message immediately above their own reply to it is the whole
    point of showing it at all.
    """
    state = _state(request)
    patient = state.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")

    thread: list[dict] = [
        {**row, "direction": "to_family"}
        for row in state.runner.outbound
        if row["patient_id"] == patient_id
    ]
    thread.extend(
        {
            "id": record.id,
            "patient_id": record.patient_id,
            "direction": "from_family",
            "kind": "message",
            "body": record.text,
            "gloss": record.gloss,
            "language": record.language,
            "channel": "whatsapp",
            "answerable": record.answerable,
            "reason": record.reason,
            "triggers": list(record.triggers),
            "sim_date": record.sim_date,
            "sent_at": record.received_at.isoformat(),
        }
        for record in state.runner.inbound
        if record.patient_id == patient_id
    )
    thread.sort(key=lambda row: row["sent_at"])

    return {
        "patient_id": patient_id,
        "language": patient.language.value,
        "thread": thread[-limit:],
        "unread": sum(1 for row in thread if row["direction"] == "to_family"),
    }


@router.post("/voice/transcribe")
async def transcribe(
    request: Request,
    audio: Annotated[UploadFile, File()],
    patient_id: Annotated[str, Form()],
    language: Annotated[str | None, Form()] = None,
) -> dict:
    """Turn a spoken reply into text. Does not act on it.

    Transcription and understanding are deliberately two calls. This one hands
    back words and a confidence the family can see and correct before anything
    is sent — mishearing a date in a language the operator does not read is not
    a failure anyone would catch later.
    """
    state = _state(request)
    patient = state.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")

    settings = state.settings
    if not settings.groq_api_key:
        raise HTTPException(
            503,
            "speech-to-text needs GROQ_API_KEY. Typing still works, and the "
            "console says so rather than failing silently.",
        )

    payload = await audio.read()
    if len(payload) < MIN_AUDIO_BYTES:
        raise HTTPException(422, "that recording was too short to transcribe")
    if len(payload) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "that recording is too long")

    # Whisper does better when told which language to expect, and we know it
    # from the patient's record rather than having to guess from the audio.
    hint = language or patient.language.value
    try:
        hint = Language(hint).value
    except ValueError:
        hint = patient.language.value

    client = groq.AsyncGroq(api_key=settings.groq_api_key)
    try:
        result = await client.audio.transcriptions.create(
            file=(audio.filename or "reply.webm", payload),
            model=settings.whisper_model,
            language=hint,
            temperature=0.0,
        )
    except groq.APIError as exc:
        logger.warning("transcription failed: %s", exc)
        # Fail closed and say so. A transcription that silently returns nothing
        # would read as "the family said nothing", which is a different claim.
        raise HTTPException(502, "could not transcribe that recording") from exc

    text = (getattr(result, "text", "") or "").strip()
    return {
        "text": text,
        "language": hint,
        "model": settings.whisper_model,
        "bytes": len(payload),
        #: Nothing has been sent. The family confirms the words first.
        "sent": False,
    }
