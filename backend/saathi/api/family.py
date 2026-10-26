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
from datetime import date
from typing import Annotated

import groq
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..domain.enums import Language, StepKind, StepStatus
from .access import FamilyOrStaff, PrincipalDep, ensure_may_see
from .deps import ContainerDep

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

#: Formats Whisper accepts, by file extension.
_AUDIO_EXTENSIONS = frozenset({"flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "wav", "webm"})

#: What a recorder's content type says when the file name is no help. A phone
#: sends m4a (AAC); a browser sends webm.
_AUDIO_BY_CONTENT_TYPE = {
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/mp4": "m4a",
    "audio/aac": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/webm": "webm",
}


def audio_filename(name: str | None, content_type: str | None) -> str:
    """A file name Whisper can read the format from.

    Whisper decides the format from the extension, so an upload with an odd or
    missing name would otherwise be rejected as unreadable even though the bytes
    are fine.
    """
    suffix = (name or "").rsplit(".", 1)[-1].lower() if "." in (name or "") else ""
    if suffix in _AUDIO_EXTENSIONS:
        return name  # type: ignore[return-value]
    guess = _AUDIO_BY_CONTENT_TYPE.get((content_type or "").split(";")[0].strip().lower(), "webm")
    return f"reply.{guess}"


#: Statuses that mean this step is behind the family rather than ahead of them.
_DONE = frozenset({StepStatus.COMPLETED, StepStatus.RESULT_AVAILABLE})


#: What the family's own screen is allowed to call a step. Deliberately the
#: vocabulary of an appointment slip — "the scan", "seeing the doctor" — not
#: the pathway's internal kind. A family does not travel to a
#: `radiology_report`; they wait for it, and nothing about the finding is here.
FAMILY_STEP_WORDS: dict[str, tuple[str, bool]] = {
    StepKind.CONSULT.value: ("Seeing the doctor", True),
    StepKind.BIOPSY.value: ("Biopsy", True),
    StepKind.BLOODS.value: ("Blood tests", True),
    StepKind.SCAN.value: ("Scan", True),
    StepKind.PET_CT.value: ("PET-CT scan", True),
    StepKind.PATHOLOGY_REPORT.value: ("Lab report", False),
    StepKind.RADIOLOGY_REPORT.value: ("Scan report", False),
    StepKind.REVIEW_CONSULT.value: ("Seeing the doctor again", True),
    StepKind.JOINT_CLINIC.value: ("Joint clinic", True),
    StepKind.TREATMENT.value: ("Treatment", True),
    StepKind.MAINTENANCE_DOSE.value: ("Next dose", True),
    StepKind.ECHO_REVIEW.value: ("Heart check and review", True),
}


class LanguageChoice(BaseModel):
    """The family naming the language they want to be written to in."""

    language: Language
    #: Who pressed it. A family member's own name where the app knows it, so
    #: the ledger row says who asked rather than "the system".
    chosen_by: str = Field(default="family", max_length=80)



@router.get("/patients/{patient_id}/notifications", dependencies=[FamilyOrStaff])
async def notifications(state: ContainerDep, patient_id: str, limit: int = 30) -> dict:
    """What this family was told, and what they said, newest last.

    One merged thread rather than two lists: a family does not experience "the
    hospital's outbound queue" and "my replies" as separate things, and reading
    the holding message immediately above their own reply to it is the whole
    point of showing it at all.
    """
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
    state: ContainerDep,
    audio: Annotated[UploadFile, File()],
    patient_id: Annotated[str, Form()],
    principal: PrincipalDep,
    language: Annotated[str | None, Form()] = None,
) -> dict:
    """Turn a spoken reply into text. Does not act on it.

    Transcription and understanding are deliberately two calls. This one hands
    back words and a confidence the family can see and correct before anything
    is sent — mishearing a date in a language the operator does not read is not
    a failure anyone would catch later.
    """
    ensure_may_see(principal, patient_id)
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
            file=(audio_filename(audio.filename, audio.content_type), payload),
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


def _latest_plan_message(runner, patient_id: str) -> dict | None:
    """The most recent thing actually sent to this family about their plan.

    Read back from the outbound record rather than re-rendered on demand: the
    family's screen must show the message that was sent, not a fresh variant of
    it. Two renders of the same plan differ in wording, and a family comparing
    their screen against the SMS they were read over the phone would find two
    different sentences with nothing to say which one counts.
    """
    for row in reversed(runner.outbound):
        if row["patient_id"] == patient_id and row["kind"] in {"plan", "holding", "answer"}:
            return row
    return None


@router.get("/patients/{patient_id}/home", dependencies=[FamilyOrStaff])
async def home(state: ContainerDep, patient_id: str) -> dict:
    """Everything the family's phone shows, in one call.

    One call rather than five because this screen is read on a 2G connection in
    a village: five round trips means five chances to show a half-built page,
    and a family reading "Come on" with no date is worse than a spinner.

    Nothing here is a finding, a result, or advice. The decision, a date, what
    is being waited for, and the words the language layer already wrote.
    """
    patient = state.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")

    run = state.runner.plans.get(patient_id)
    plan = run.plan if run else None
    message = _latest_plan_message(state.runner, patient_id)

    steps = []
    for step in sorted(
        state.world.steps_for(patient_id),
        key=lambda s: (s.scheduled_for or s.result_available_on or s.completed_on or date.max),
    ):
        word, travels = FAMILY_STEP_WORDS.get(
            step.kind.value, (step.kind.value.replace("_", " "), True)
        )
        when = step.scheduled_for or step.completed_on or step.result_available_on
        steps.append(
            {
                "id": step.id,
                #: The console translates this; `what` is the English fallback.
                "kind": step.kind.value,
                "what": word,
                "when": when.isoformat() if when else None,
                #: Done, waiting, or still to come — three states, because a
                #: family tracking a journey needs no more than three.
                "state": (
                    "done"
                    if step.status in _DONE
                    else "waiting"
                    if step.status is StepStatus.PENDING_RESULT
                    else "ahead"
                ),
                "travels": travels,
                "is_next": bool(plan and step.id == plan.target_step_id),
            }
        )

    return {
        "patient": {
            "id": patient.id,
            "district": patient.home_district,
            "language": patient.language.value,
            "distance_km": round(patient.home_distance_km),
            "hours_each_way": state.runner.journey_hours(patient),
        },
        "decision": plan.decision.value if plan else None,
        "travel_on": plan.travel_on.isoformat() if plan and plan.travel_on else None,
        #: Why, in the shape a family asks it: what is being waited for and
        #: when it is expected. Never a probability, never a score.
        "waiting_for": [
            {
                "kind": b.kind.value,
                "what": FAMILY_STEP_WORDS.get(b.kind.value, (b.kind.value, True))[0],
                "earliest": b.expected_ready.earliest.isoformat() if b.expected_ready else None,
                "latest": b.expected_ready.latest.isoformat() if b.expected_ready else None,
                "certain": bool(
                    b.expected_ready
                    and b.expected_ready.earliest == b.expected_ready.latest
                ),
            }
            for b in (plan.blocked_by if plan else ())
        ],
        "message": (
            {
                "body": message["body"],
                "language": message["language"],
                "kind": message["kind"],
                "sent_at": message["sent_at"],
                #: A held message was never sent. Saying so is the honest thing
                #: to put on the family's screen, and it is why the phone shows
                #: "a person is calling you" instead of a sentence.
                "held": message["held"],
                "written_by": message["rendered_by"],
            }
            if message
            else None
        ),
        "steps": steps,
        #: For a family cleared to travel: what to carry and the first desk to
        #: reach. Logistics only, the same list the navigator's checklist shows.
        "what_to_bring": list(plan.what_to_bring) if plan else [],
        "where_to_go_first": plan.where_to_go_first if plan else None,
        "sim_date": state.world.today.isoformat(),
        "updated_at": run.computed_at.isoformat() if run else None,
    }


@router.patch("/patients/{patient_id}/language", dependencies=[FamilyOrStaff])
async def choose_language(state: ContainerDep, patient_id: str, body: LanguageChoice) -> dict:
    """The family picks their language. Every message after this obeys.

    A real change to their record, logged and re-rendered — not a translation
    of the screen. The labels on the phone come from a static table, because
    "Plan" is chrome; everything the system *says* is re-written by the
    language layer and re-checked by the guard.
    """
    result = await state.runner.set_language(patient_id, body.language)
    if result is None:
        raise HTTPException(404, "unknown patient")

    run = state.runner.plans.get(patient_id)
    message = _latest_plan_message(state.runner, patient_id)
    return {
        **result,
        "chosen_by": body.chosen_by,
        "rendered": bool(run and run.message and not run.message.routed_to_care_team),
        "message": {"body": message["body"], "held": message["held"]} if message else None,
    }
