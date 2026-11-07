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

import asyncio
import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from .. import orchestrator
from ..adapters.speech import GroqWhisper, SarvamSpeech
from ..domain.budget import TOPIC_NEED, BudgetAnswer, BudgetAsk, BudgetTopic
from ..domain.enums import Language, ReadinessKind, StepKind, StepStatus
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


def _listeners(settings) -> list:
    """Who gets asked to listen, best first.

    Sarvam leads because these are Indian-language families with Indian
    accents, and it is the service built for them. Whisper follows because it
    is usually configured anyway, and a second opinion costs nothing when the
    first one returns nothing.
    """
    listeners = []
    if settings.sarvam_api_key:
        listeners.append(
            SarvamSpeech(
                settings.sarvam_api_key,
                listen_model=settings.sarvam_listen_model,
                speak_model=settings.sarvam_speak_model,
            )
        )
    if settings.groq_api_key:
        listeners.append(GroqWhisper(settings.groq_api_key, settings.whisper_model))
    return listeners


def _speaker(settings):
    """Who reads a message out.

    Only Sarvam can. Whisper has no voice at all, and no browser ships an Odia
    one — so without this configured, an Odia family's read-aloud button is a
    control that does nothing.
    """
    if not settings.sarvam_api_key:
        return None
    return SarvamSpeech(
        settings.sarvam_api_key,
        listen_model=settings.sarvam_listen_model,
        speak_model=settings.sarvam_speak_model,
    )


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
    StepKind.DIALYSIS_SESSION.value: ("Dialysis session", True),
    StepKind.NEPHROLOGY_REVIEW.value: ("Kidney doctor review", True),
    StepKind.DISCHARGE_REVIEW.value: ("Check-up after leaving hospital", True),
    StepKind.WOUND_CHECK.value: ("Dressing check", True),
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

    A message the guard diverted has no words (staff see why on the control
    centre), so it is not part of what the family was told and is left out.

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
        if row["patient_id"] == patient_id and row["body"]
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
    listeners = _listeners(settings)
    if not listeners:
        raise HTTPException(
            503,
            "speech-to-text needs SARVAM_KEY or GROQ_API_KEY. Typing still "
            "works, and the app says so rather than failing silently.",
        )

    payload = await audio.read()
    if len(payload) < MIN_AUDIO_BYTES:
        raise HTTPException(422, "that recording was too short to transcribe")
    if len(payload) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "that recording is too long")

    # Both services do better when told which language to expect, and we know
    # it from the patient's record rather than guessing from the audio.
    hint = language or patient.language.value
    try:
        hint = Language(hint).value
    except ValueError:
        hint = patient.language.value

    filename = audio_filename(audio.filename, audio.content_type)
    heard = None
    for listener in listeners:
        heard = await asyncio.to_thread(listener.transcribe, payload, filename, hint)
        if heard is not None:
            break
        logger.info("%s heard nothing; trying the next listener", listener.describe())
    if heard is None:
        # Fail closed and say so. A transcription that silently returns nothing
        # would read as "the family said nothing", which is a different claim.
        raise HTTPException(502, "could not transcribe that recording")

    return {
        "text": heard.text,
        "language": heard.language,
        "model": heard.heard_by,
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
        said = row["kind"] in {"plan", "holding", "answer"} and row["body"]
        if row["patient_id"] == patient_id and said:
            return row
    return None


async def _guide(state: ContainerDep, patient_id: str) -> dict | None:
    from .guide import guide_for

    found = await guide_for(state, patient_id)
    return found.model_dump(mode="json") if found else None


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
        #: The whole journey in order, from the first test to the doctor: what is
        #: done, who has what, and what the family should do now.
        "guide": (await _guide(state, patient_id)),
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


class SayThis(BaseModel):
    """Text to read out. Already written by the language layer and already
    passed by the guard — this endpoint reads, it never composes."""

    text: str = Field(min_length=1, max_length=1200)
    language: str | None = None


@router.post("/patients/{patient_id}/voice/say", dependencies=[FamilyOrStaff])
async def say(state: ContainerDep, patient_id: str, body: SayThis) -> Response:
    """Read a message out, in the family's own language.

    The family app used the browser's own speech for this, which has no Odia
    voice at all — the button existed and did nothing, silently, for every Odia
    family. This hands back real audio instead.

    It will only read text; it cannot be made to say something the guard has
    not already passed, because it is given the message rather than the plan.
    """
    patient = state.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")

    speaker = _speaker(state.settings)
    if speaker is None:
        raise HTTPException(
            503,
            "reading aloud needs SARVAM_KEY. The message is still on screen, "
            "and the app says so rather than offering a button that does nothing.",
        )

    language = body.language or patient.language.value
    try:
        language = Language(language).value
    except ValueError:
        language = patient.language.value

    spoken = await asyncio.to_thread(speaker.say, body.text, language)
    if spoken is None:
        raise HTTPException(502, "could not read that out")
    return Response(
        content=spoken.audio,
        media_type=spoken.media_type,
        headers={
            "Cache-Control": "no-store",
            "X-Spoken-By": spoken.spoken_by,
            "Content-Language": language,
        },
    )


# ---------------------------------------------------------------- budget ----
#
# What the family can actually manage. See `domain/budget.py` for why this is a
# conversation rather than a setting: the planner can work out that a journey
# needs a ride and a bed, and cannot work out whether this household can pay
# for the ones it picked.


def _desk(state):
    """The partner desk, when partners are switched on.

    It is the one object holding the onboarding store, so it is the one that
    can say what a family told us and write down what they choose.
    """
    return state.runner.partners


def _asks(state, patient) -> list[BudgetAsk]:
    """The budget questions worth putting to this family, in journey order.

    Only about parts of the trip they actually have. A family going home the
    same evening is never asked which hotel they can afford, and a question
    with no real organisation behind it is not asked at all.
    """
    desk = _desk(state)
    registry = state.registry
    if desk is None or registry is None:
        return []
    #: Only the needs this journey actually has. The desk has already worked
    #: that out and written a row for each; asking about a stay this family
    #: does not need is the kind of question that makes people stop reading.
    needs = {item.kind for item in state.world.readiness_for(patient.id)}
    hospital = next((h for h in registry.hospitals() if h.id == patient.hospital_id), None)
    organisations = registry.organisations()
    means = desk.means_for(patient.id)
    out = []
    for topic in orchestrator.topics_worth_asking(needs):
        need = TOPIC_NEED[topic]
        at_hospital = need in {ReadinessKind.STAY, ReadinessKind.MEDICINE}
        place = (hospital.place if (at_hospital and hospital) else patient.home_district)
        ask = orchestrator.offer(
            topic,
            patient_id=patient.id,
            district=place,
            hospital_id=patient.hospital_id,
            organisations=organisations,
            means=means,
        )
        if ask.answerable:
            out.append(ask)
    return out


@router.get("/patients/{patient_id}/budget", dependencies=[FamilyOrStaff])
async def budget(state: ContainerDep, patient_id: str) -> dict:
    """What this family is being asked about cost, and what they have said.

    Every option named here is a real organisation that serves this family's
    district and works with their hospital. Nothing is composed for the screen,
    and nothing carries an amount: this project does not report a fare it was
    not given.
    """
    patient = state.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")
    asks = _asks(state, patient)
    answers = state.runner.budget_answers_for(patient_id)
    return {
        "asks": [
            {
                "topic": ask.topic.value,
                "need": ask.need.value,
                "options": [
                    {
                        "organisation_id": o.organisation_id,
                        "name": o.name,
                        #: The organisation's own words from the directory, not
                        #: a label written for this screen.
                        "what": list(o.what),
                        "cost_tier": o.cost_tier.value,
                        "suggested": o.suggested,
                    }
                    for o in ask.options
                ],
                #: Always offered, always last. The most important answer, and
                #: the one a priced menu usually has no room for.
                "can_say_cannot_manage": True,
                "answered": ask.topic.value in answers,
            }
            for ask in asks
        ],
        "answers": [a.model_dump(mode="json") for a in answers.values()],
    }


class BudgetReply(BaseModel):
    """What the family tapped, or said."""

    #: The organisation they chose. Omit it with `cannot_manage` set.
    organisation_id: str | None = Field(default=None, max_length=64)
    #: "I cannot manage any of these." Routed to the social-work desk.
    cannot_manage: bool = False
    #: Their own words, when they spoke rather than tapped, so a navigator can
    #: check the transcription against the option it was matched to.
    said: str = Field(default="", max_length=400)


@router.post("/patients/{patient_id}/budget/{topic}", dependencies=[FamilyOrStaff])
async def answer_budget(
    state: ContainerDep, patient_id: str, topic: BudgetTopic, body: BudgetReply
) -> dict:
    """Record what the family said. Nothing moves until a navigator agrees.

    A proposal, like `PatientRequest`, and for the same reason: a tapped option
    is safer than prose but a *spoken* one has been through a transcriber, and
    that is exactly the kind of reading that must not be believed on sight.
    """
    patient = state.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")
    if not body.cannot_manage and not body.organisation_id:
        raise HTTPException(422, "choose an organisation or say you cannot manage")

    answer = BudgetAnswer(
        patient_id=patient_id,
        topic=topic,
        organisation_id=None if body.cannot_manage else body.organisation_id,
        needs_help=body.cannot_manage,
        said=body.said,
    )
    state.runner.record_budget_answer(answer)
    return {"recorded": True, "awaiting_confirmation": True, "topic": topic.value}
