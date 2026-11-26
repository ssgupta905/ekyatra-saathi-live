"""The Groq actors.

Four jobs, and a rule that decides all four: **an actor may produce an input or
a reading, never a decision.** It can write the ward note a hospital would have
written, write the message a caregiver would have sent, summarise records a
navigator already has in front of them, or say an existing sentence in another
language. It cannot decide whether a family travels, cannot bound a readiness
window, and cannot rank an alert. Those stay in code, where they can be read.

So being wrong is cheap everywhere here:

* a bad ward note is caught by the parser and then by a human confirming it;
* a bad caregiver message is just an odd thing for a family to have asked, and
  the real guard screens it like any other;
* a brief line with no resolvable ledger id is dropped before anyone sees it;
* a narrated sentence goes through `guard.check_outbound` against the same plan
  as the message would.

Every method returns None on any failure. The world must keep turning when the
API does not, so nothing in here is allowed to raise into the tick loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import groq

from ..domain.enums import DisruptionKind, StepStatus
from ..domain.models import CareStep, Patient, Resource
from ..language import guard
from ..language.rendering import LANGUAGE_NAMES
from ..ports.ledger import EvidenceLedger
from .world import LiveWorld

logger = logging.getLogger(__name__)

MODEL = "openai/gpt-oss-120b"


#: Ten fields plus a reasoning pass do not fit in the shared 700-token cap.
#: Measured, not guessed: at 700 this schema fails outright on a message
#: carrying both a date and a figure.
_REQUEST_TOKENS = 2000

#: The largest journey figure this will accept from a reading, in rupees. A
#: family saying "nine hundred" and a model returning 900000 look identical
#: downstream, so the implausible one is dropped rather than recorded. A real
#: journey above this is a conversation for a navigator, not a silent number.
_MOST_A_JOURNEY_COSTS = 100_000

#: Nobody travels to a hospital with more companions than this. A reading that
#: says otherwise misread something, and dropping it costs one question.
_MOST_COMPANIONS = 10


#: Longest we will wait out a rate limit before giving the message to a
#: person instead. Groq's own `Please try again in Ns` is usually under 20.
_MOST_BACKOFF = 25.0


def _retry_after(exc: Exception) -> float:
    """How long the API asked us to wait, from its own message.

    Read out of the text rather than guessed, because the number is right
    there and a fixed sleep is either rude or too slow. Falls back to a few
    seconds when the message is not in the shape we expect — a changed error
    format should cost a retry, not an exception inside an error handler.
    """
    found = re.search(r"try again in ([0-9.]+)s", str(exc))
    if not found:
        return 5.0
    try:
        return min(float(found.group(1)) + 0.5, _MOST_BACKOFF)
    except ValueError:
        return 5.0


def _as_count(raw: object, *, most: int = _MOST_COMPANIONS) -> int | None:
    """A non-negative count, or None for anything that is not plainly one.

    `None` and an unreadable value are deliberately the same answer: both mean
    "nobody told us", which is what the caller must act on. Returning 0 instead
    would read as "they said nobody is coming".
    """
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= most else None


def _as_flag(raw: object) -> bool | None:
    """A yes or a no the family actually gave, or None."""
    return raw if isinstance(raw, bool) else None


def _schema(name: str, properties: dict, required: list[str]) -> dict:
    """Strict structured output: every field required, nothing extra."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


WARD_NOTE_SCHEMA = _schema(
    "ward_note",
    {
        "note": {
            "type": "string",
            "description": (
                "One or two sentences of ward shorthand, as a busy clerk types it."
            ),
        }
    },
    ["note"],
)

PARSED_NOTE_SCHEMA = _schema(
    "parsed_note",
    {
        "step_id": {"type": "string"},
        "new_status": {
            "type": "string",
            "enum": [s.value for s in StepStatus],
        },
        "released_on": {
            "type": "string",
            "description": "ISO date the note says the result became available.",
        },
        "confidence": {"type": "string", "enum": ["high", "low"]},
    },
    ["step_id", "new_status", "released_on", "confidence"],
)

CAREGIVER_SCHEMA = _schema(
    "caregiver_message",
    {
        "text": {
            "type": "string",
            "description": "What the caregiver types, in their own language.",
        },
        "english_gloss": {
            "type": "string",
            "description": "Literal English translation, for the navigator.",
        },
    },
    ["text", "english_gloss"],
)

BRIEF_SCHEMA = _schema(
    "call_brief",
    {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "ledger_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "ledger_ids"],
                "additionalProperties": False,
            },
        }
    },
    ["lines"],
)

REQUEST_SCHEMA = _schema(
    "patient_request",
    {
        "intent": {
            "type": "string",
            "enum": [
                "move_visit", "change_centre", "ask_status", "needs_help", "unclear",
            ],
        },
        "step_kind": {
            "type": "string",
            "description": (
                "Which step they want moved, as one of the hospital's step names, "
                "or an empty string if they did not name one."
            ),
        },
        "not_before": {
            "type": "string",
            "description": "Earliest ISO date they could come, or empty string.",
        },
        "not_after": {
            "type": "string",
            "description": "Latest ISO date they could come, or empty string.",
        },
        "excluded_dates": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Single days they say they cannot travel, as ISO dates. "
                '"We cannot come on the 11th" is one entry here, not a '
                "not_before or a not_after. Empty array if they name none."
            ),
        },
        "reason": {
            "type": "string",
            "description": "Why, in plain English. Never a clinical reason.",
        },
        "confidence": {"type": "string", "enum": ["high", "low"]},
        # Travel facts. `null` is the honest answer for anything the message
        # did not say, and the system prompt insists on it — a 0 companions or
        # a guessed fare would be indistinguishable from a real answer.
        "companions": {
            "type": ["integer", "null"],
            "description": (
                "How many people travel WITH the patient, NOT counting the patient. "
                "\"I will go with him\" is 1. \"My brother and I will come\" is 2. "
                "\"Two of us are coming\" is 1 when one of the two is the patient, "
                "and the message usually makes that clear. \"I am coming alone\", "
                "said by the patient, is 0. Null only when the message does not say. "
                "Never guess from household size."
            ),
        },
        "single_day_trip": {
            "type": ["boolean", "null"],
            "description": (
                "True if they say they can go and return the same day, false if "
                "they say they must stay a night, null if the message is silent."
            ),
        },
        "stated_cost_inr": {
            "type": ["integer", "null"],
            "description": (
                "A money amount THE FAMILY STATES for travel or the trip, as a "
                "plain number. Families say this in many words and all of them "
                "count: rupees, rupaye, rupaiya, taka, taka, Rs, \u20b9, or just a "
                "number next to tickets, fare, bus, train, kharcha or kharach. "
                "\"Train tickets will be 900 taka\" is 900. \"Bus ka ticket 1400 ka\" "
                "is 1400. Treat every one of these as the same field; do not "
                "convert between currencies. Only a figure they actually said — "
                "never your own estimate of a fare. Null if they stated none."
            ),
        },
        "refundable": {
            "type": ["boolean", "null"],
            "description": (
                "If they mention a ticket or booking they have already paid for: "
                "true if it can be changed or refunded, false if it cannot, null "
                "if they do not say or mention no booking."
            ),
        },
    },
    [
        "intent", "step_kind", "not_before", "not_after", "excluded_dates",
        "reason", "confidence",
        "companions", "single_day_trip", "stated_cost_inr", "refundable",
    ],
)

NARRATION_SCHEMA = _schema(
    "narration",
    {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        }
    },
    ["nodes"],
)


WARD_NOTE_SYSTEM = """\
You are a hospital records clerk in a large Indian cancer centre, typing a line \
into the day's release log. Write the way a busy clerk writes: short, clipped, \
abbreviations, no greeting, no explanation.

Say only that the named report has been released and when. Never say anything \
about what the report contains — you are logging that it exists, not what it \
found. No diagnosis, no findings, no impression, no reassurance.
"""

DISRUPTION_SCHEMA = _schema(
    "disruption_reading",
    {
        "resource_id": {
            "type": "string",
            "description": "The id of the resource the note is about, from the list given.",
        },
        "kind": {"type": "string", "enum": [k.value for k in DisruptionKind]},
        "unavailable_from": {"type": "string", "description": "ISO date, YYYY-MM-DD."},
        "unavailable_to": {
            "type": "string",
            "description": "ISO date, or empty when the note gives no end.",
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "read_as": {
            "type": "string",
            "description": "One short sentence: what you took the note to mean.",
        },
    },
    ["resource_id", "kind", "unavailable_from", "unavailable_to", "confidence", "read_as"],
)

DISRUPTION_SYSTEM = """\
You read a line from a hospital department's work log and extract the outage it \
describes: which resource, what kind of outage, and for how long.

Pick `resource_id` only from the list you are given. If the note names something \
not on that list, pick the closest and mark confidence "low" — a desk clerk will \
confirm or correct this before anything happens, so a wrong guess is cheap and a \
refusal to guess is not helpful.

Dates: resolve relative words ("till Saturday", "for two days", "this week") \
against the date you are given. Leave `unavailable_to` empty when the note gives \
no end, rather than inventing one.

You are reading logistics, never clinical information. A note that is about a \
patient rather than a resource is not an outage: mark confidence "low".
"""

PARSE_SYSTEM = """\
You read a hospital clerk's free-text release note and extract the structured \
record update it implies. Extract only what the note actually says. If the note \
names a different step than the one you were given, return the one the note \
names — a mismatch is for the reviewer to catch, not for you to paper over. \
Mark confidence "low" whenever the note is ambiguous.
"""

CAREGIVER_SYSTEM = """\
You are writing as the family member of a cancer patient from a small town in \
eastern India, messaging the hospital's helpline on WhatsApp. You are tired, \
your money is tight, and the journey to the hospital is long and expensive.

Write one short message in your own language, the way a real person types on a \
phone — informal, transliterated or in script, sometimes without punctuation. \
Do not write like a form. Do not be polite at length.

You will be told what kind of worry is on your mind. Write only that message. \
Never write as the hospital; you are the family.
"""

BRIEF_SYSTEM = """\
You prepare a patient navigator for a phone call to a family. The navigator has \
seconds, so write at most four short lines: what changed since the last contact, \
what signal is open, what the family last asked, and what the system has already \
told them.

You are given records. Every line you write must cite the ledger ids of the \
records it rests on, and you may state nothing that is not in them. If you \
cannot support a line, leave it out — a short brief is useful, an invented one \
is dangerous.

Never write anything clinical: no diagnosis, no findings, no advice. You are \
briefing on logistics and contact history only.
"""

REQUEST_SYSTEM = """\
You read one message from a patient's family and work out what they are asking \
the hospital to change. You are not deciding anything and you are not replying \
to them; a navigator reads your answer and confirms it before anything moves.

Extract only what the message actually says:

- `move_visit` when they want a booked visit on a different date.
- `change_centre` when they ask whether something can happen somewhere else or \
nearer to them.
- `ask_status` when they only want to know what is happening.
- `needs_help` when the difficulty is money, paperwork or transport rather than \
a date.
- `unclear` whenever you are not sure. Guessing costs a family a journey; \
`unclear` costs a navigator ten seconds of reading.

Dates must be real ISO dates you can justify from the message and today's date. \
"After the 20th" with today in December means not_before is the 20th of that \
December. A day of the month that has already passed this month means the next \
one: "not before the 1st" on the 25th of November is the 1st of December, and \
"not before the 15th" on the 25th of November is the 15th of December. Work the \
date out and put it in the field — a date left in `reason` instead of \
`not_before` or `not_after` cannot be acted on by anybody. If a date genuinely \
cannot be worked out, leave it empty rather than estimating.

Never record a clinical reason. If the message says somebody is unwell, that is \
not a scheduling request — return `unclear` and let a person handle it.

Four more fields record what the family said about the journey itself: how many \
people are coming, whether they can return the same day, any rupee figure they \
stated, and whether a ticket they have already bought can be changed. Use null \
for every one of these the message does not answer. Do not infer a fare from a \
distance, a mode of travel or anything you know about prices: if they did not \
say a number, there is no number. A figure you supplied would be read by a \
hospital as something the family told us, which would be false.
"""

NARRATION_SYSTEM = """\
You translate a patient navigator's on-screen explanation into the family's own \
language, so the navigator can read it aloud on the phone.

Translate faithfully. Add nothing, soften nothing, promise nothing. If the \
English says there is no date, the translation says there is no date. Keep each \
line short enough to say in one breath. Never introduce anything clinical.
"""


@dataclass
class GroqActors:
    """Groq-backed actors. Constructed only when `GROQ_API_KEY` is present."""

    api_key: str
    world: LiveWorld
    model: str = MODEL
    #: Rough ceiling on concurrent actor work, so a slow API cannot pile up.
    max_tokens: int = 700

    def __post_init__(self) -> None:
        self._client = groq.AsyncGroq(api_key=self.api_key)

    def describe(self) -> str:
        return f"Groq · {self.model}"

    # ---------------- transport ----------------

    async def _json(
        self,
        system: str,
        prompt: str,
        response_format: dict,
        temperature: float = 0.6,
        max_tokens: int | None = None,
    ) -> dict[str, Any] | None:
        """One structured call. Returns None on anything that is not clean JSON.

        `max_tokens` overrides the shared cap for one call. This matters more
        than it looks: these are reasoning models, the reasoning is spent out
        of the same budget as the answer, and a cap too small for the schema
        comes back as `json_validate_failed` with an empty `failed_generation`
        — a message that points at the prompt when the cause is the ceiling.
        """
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens or self.max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format=response_format,
            )
            text = response.choices[0].message.content
        except groq.RateLimitError as exc:
            # The free tier is 8,000 tokens a minute, and this system can
            # legitimately want several readings at once — a connector poll
            # that finds three families affected by the same leave asks three
            # times in a second. Measured on a real key: concurrent calls 429
            # perfectly reliably, and the failure is indistinguishable
            # downstream from "the family said nothing", which is the worst
            # possible way to lose a reading.
            #
            # One retry, after the wait the API itself asks for. Not a loop:
            # if the budget is genuinely gone, a person reading the message
            # is the right outcome and a queue of retries only delays it.
            wait = _retry_after(exc)
            logger.warning("rate limited; retrying once in %.1fs", wait)
            await asyncio.sleep(wait)
            try:
                response = await self._client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens or self.max_tokens,
                    temperature=temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    response_format=response_format,
                )
                text = response.choices[0].message.content
            except (groq.APIError, IndexError, AttributeError) as retry_exc:
                logger.warning("actor call failed after a retry: %s", retry_exc)
                return None
        except (groq.APIError, IndexError, AttributeError) as exc:
            logger.warning("actor call failed: %s", exc)
            return None
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("actor returned unparseable json")
            return None

    # ---------------- a. the ward note ----------------

    async def draft_ward_note(self, step: CareStep, today: date) -> str | None:
        prompt = (
            f"Report step id: {step.id}\n"
            f"Report type: {step.kind.value.replace('_', ' ')}\n"
            f"Queue: {step.queue}\n"
            f"Released on: {today.isoformat()}\n"
            f"Patient reference: {step.patient_id}"
        )
        data = await self._json(WARD_NOTE_SYSTEM, prompt, WARD_NOTE_SCHEMA, 0.8)
        if data is None:
            return None
        note = str(data.get("note", "")).strip()
        if not note:
            return None
        # A clerk's note must not carry findings. If the actor slipped, drop it
        # and let the template stand in — the fallback is never worse than this.
        if not guard.screen_inbound(note).allowed:
            logger.warning("drafted ward note tripped the clinical guard; discarding")
            return None
        return note

    async def parse_ward_note(self, note: str, expected_step_id: str) -> dict | None:
        """Turn the note back into a record update, and refuse to guess.

        The parse is rejected outright if it names a step that is not in the
        world or a status outside the enum. A desk clerk should be confirming a
        record, not a hallucination.
        """
        prompt = (
            f"Note: {note}\n"
            f"Step id this note was filed against: {expected_step_id}\n"
            f"Today: {self.world.today.isoformat()}"
        )
        data = await self._json(PARSE_SYSTEM, prompt, PARSED_NOTE_SCHEMA, 0.1)
        if data is None:
            return None

        step_id = str(data.get("step_id", ""))
        if self.world.step(step_id) is None:
            logger.warning("parsed note names unknown step %r; rejecting", step_id)
            return None
        try:
            status = StepStatus(str(data.get("new_status")))
        except ValueError:
            logger.warning("parsed note has an unknown status; rejecting")
            return None
        try:
            released_on = date.fromisoformat(str(data.get("released_on")))
        except ValueError:
            released_on = self.world.today

        return {
            "step_id": step_id,
            "new_status": status.value,
            "released_on": released_on.isoformat(),
            "confidence": str(data.get("confidence", "low")),
            "matches_expected": step_id == expected_step_id,
            "source": "groq",
        }

    # ---------------- b. what the family writes in ----------------

    async def read_work_log(
        self, text: str, resources: Sequence[Resource], today: date
    ) -> dict | None:
        """Read a department's own words and propose an outage from them.

        A desk does not think in `resource_id` and `unavailable_to`. It thinks
        "MRI-2 down till Saturday" and types that into a log it already keeps.
        This reads that line and proposes the record it implies — it never
        raises one. The desk sees what was understood and confirms it, so the
        model supplies a reading and a person still supplies the decision.
        """
        catalogue = "\n".join(
            f"  {r.id} — {r.display_name} ({r.kind.value}, {r.department or 'no department'})"
            for r in resources
        )
        prompt = (
            f"Today: {today.isoformat()}\n"
            f"Resources that can be reported:\n{catalogue}\n\n"
            f"Work log line:\n{text.strip()[:600]}"
        )
        data = await self._json(DISRUPTION_SYSTEM, prompt, DISRUPTION_SCHEMA, 0.2)
        if data is None:
            return None

        # The model picks from a list; trust nothing it returns that is not on it.
        known = {r.id for r in resources}
        if str(data.get("resource_id")) not in known:
            logger.warning("work-log reading named an unknown resource; discarding")
            return None
        try:
            DisruptionKind(str(data.get("kind")))
        except ValueError:
            return None
        return data

    async def write_caregiver_message(
        self, patient: Patient, plan_run: Any | None, kind: str | None = None
    ) -> tuple[str, str] | None:
        """Write one inbound message. The real guard screens it afterwards.

        `kind` nudges the subject so an operator can force the moment they want
        to show; left unset, the actor picks from the family's situation.
        """
        decision = getattr(getattr(plan_run, "plan", None), "decision", None)
        waiting_on = ", ".join(
            b.kind.value.replace("_", " ")
            for b in getattr(getattr(plan_run, "plan", None), "blocked_by", ()) or ()
        )
        subject = {
            "clinical_question": (
                "You want to know what the report says, or what the illness means. "
                "Ask it plainly."
            ),
            "logistics_question": (
                "You want to know about the journey, the cost, the paperwork, or "
                "when to come. Ask about that only."
            ),
            "chasing": "You have not heard anything for days and you are anxious about it.",
            "process_question": (
                "Something you were booked for has been disturbed. You want to know "
                "what happens to it now and when you will be told — not what it means "
                "medically. Ask about the arrangement."
            ),
        }.get(kind or "", "Write whatever is most on your mind right now.")

        prompt = (
            f"Your language: {LANGUAGE_NAMES.get(patient.language, 'Hindi')}\n"
            f"Your district: {patient.home_district}, "
            f"{patient.home_distance_km:.0f} km from the hospital\n"
            f"What the hospital last told you: "
            f"{decision.value if decision else 'nothing yet'}\n"
            f"Still outstanding: {waiting_on or 'nothing you know of'}\n\n"
            f"{subject}"
        )
        data = await self._json(CAREGIVER_SYSTEM, prompt, CAREGIVER_SCHEMA, 0.9)
        if data is None:
            return None
        text = str(data.get("text", "")).strip()
        if not text:
            return None
        return text, str(data.get("english_gloss", "")).strip()

    # ---------------- c. the call-prep brief ----------------

    async def call_prep_brief(
        self,
        patient: Patient,
        plan_run: Any | None,
        steps: list[CareStep],
        ledger: EvidenceLedger,
        alerts: list,
        inbound: list,
    ) -> list[dict] | None:
        """Four lines for the navigator, each with a citation that resolves.

        The enforcement is here, not in the prompt: a line whose ledger ids do
        not all exist is dropped before it reaches the screen, so every chip on
        the brief opens a real row.
        """
        entries = ledger.for_patient(patient.id)
        if not entries:
            return []

        records = "\n".join(
            f"- [{e.id}] {e.claim} (source: {e.source.value}, "
            f"recorded {e.recorded_at:%d %b %H:%M})"
            for e in entries[-20:]
        )
        plan = getattr(plan_run, "plan", None)
        signals = "\n".join(
            f"- {a.kind.value}: {a.detail[:120]}" for a in alerts if a.patient_id == patient.id
        )
        asked = "\n".join(
            f"- {r.text[:160]}" + (f"  (English: {r.gloss})" if r.gloss else "")
            for r in inbound
            if r.patient_id == patient.id
        )
        prompt = (
            f"Family: {patient.id}, {patient.home_district}, "
            f"{LANGUAGE_NAMES.get(patient.language, '')}, "
            f"{patient.home_distance_km:.0f} km away\n"
            f"Current decision: {plan.decision.value if plan else 'none'}"
            f"{f' — travel {plan.travel_on}' if plan and plan.travel_on else ''}\n"
            f"Steps on record: "
            f"{', '.join(f'{s.kind.value}={s.status.value}' for s in steps)}\n\n"
            f"LEDGER RECORDS (cite these ids):\n{records}\n\n"
            f"OPEN SIGNALS:\n{signals or '- none'}\n\n"
            f"WHAT THEY HAVE WRITTEN IN:\n{asked or '- nothing'}"
        )
        data = await self._json(BRIEF_SYSTEM, prompt, BRIEF_SCHEMA, 0.3)
        if data is None:
            return None

        known = {e.id for e in entries}
        lines: list[dict] = []
        for raw in data.get("lines", [])[:4]:
            text = str(raw.get("text", "")).strip()
            ids = [str(i) for i in raw.get("ledger_ids", [])]
            if not text or not ids:
                continue
            if not set(ids) <= known:
                logger.info("dropping brief line with an unresolvable citation")
                continue
            if not guard.screen_inbound(text).allowed:
                continue
            lines.append({"text": text, "ledger_ids": ids})
        return lines

    # ---------------- e. reading what the family asked for ----------------

    async def extract_request(
        self,
        patient: Patient,
        text: str,
        today: date,
        *,
        known_steps: tuple[str, ...] = (),
    ) -> dict | None:
        """Read a family's message into a structured ask, for a person to confirm.

        Returns a dict shaped for `PatientRequest`, or None when the call failed.
        Nothing here is believed on sight — the caller leaves `confirmed_by`
        empty and a navigator agrees with the reading before the planner sees it.
        """
        prompt = (
            f"Today is {today.isoformat()}.\n"
            f"The family writes in {LANGUAGE_NAMES.get(patient.language, 'Hindi')}.\n"
            f"Steps this patient has booked: {', '.join(known_steps) or 'unknown'}\n\n"
            f"Message: {text}"
        )
        data = await self._json(
            REQUEST_SYSTEM, prompt, REQUEST_SCHEMA, 0.1, max_tokens=_REQUEST_TOKENS
        )
        if data is None:
            logger.warning(
                "could not read %s's message into a request; treating it as no answer",
                patient.id,
            )
            return None

        def as_date(raw: str) -> str | None:
            raw = str(raw or "").strip()
            if not raw:
                return None
            try:
                return date.fromisoformat(raw).isoformat()
            except ValueError:
                # An unparseable date is no date. Better a navigator asks than
                # the planner acts on a month that was never said.
                return None

        step = str(data.get("step_kind", "")).strip()

        # The prompt says "never a clinical reason". A prompt is a request, so
        # check it: a reading that smuggled a diagnosis into the free-text
        # field would put it on a navigator's screen and into storage.
        reason = str(data.get("reason", "")).strip()
        if reason and not guard.screen_inbound(reason).allowed:
            logger.warning("a request reading carried a clinical reason; dropping it")
            reason = ""

        return {
            "intent": str(data.get("intent", "unclear")),
            "step_kind": step if step in known_steps else None,
            "not_before": as_date(data.get("not_before", "")),
            "not_after": as_date(data.get("not_after", "")),
            "excluded_dates": tuple(
                dict.fromkeys(  # a day said twice is one day
                    kept
                    for raw in (data.get("excluded_dates") or [])
                    if (kept := as_date(raw)) is not None
                )
            ),
            "reason": reason,
            "confidence": str(data.get("confidence", "low")),
            # Travel facts travel together with the sentence they were read
            # from: a figure with no utterance behind it is refused downstream
            # by `PatientRequest.travel_is_attributable`.
            "companions": _as_count(data.get("companions")),
            "single_day_trip": _as_flag(data.get("single_day_trip")),
            "stated_cost_inr": _as_count(
                data.get("stated_cost_inr"), most=_MOST_A_JOURNEY_COSTS
            ),
            "refundable": _as_flag(data.get("refundable")),
        }

    # ---------------- d. trace narration ----------------

    async def narrate_trace(
        self,
        nodes: list[dict],
        patient: Patient,
        plan_run: Any | None,
        ledger: EvidenceLedger,
    ) -> list[dict] | None:
        """Say the navigator's own explanation in the family's language.

        Each narrated line is put through `guard.check_outbound` against the
        patient's current plan — the same check the outbound message passes. A
        line that fails comes back marked held rather than quietly dropped, so
        the navigator knows to say it themselves.
        """
        plan = getattr(plan_run, "plan", None)
        if plan is None or not nodes:
            return []

        listing = "\n".join(f"[{n.get('id')}] {n.get('text', '')}" for n in nodes[:8])
        prompt = (
            f"Target language: {LANGUAGE_NAMES.get(patient.language, 'Hindi')}\n"
            f"The decision is: {plan.decision.value}"
            f"{f' — travel {plan.travel_on}' if plan.travel_on else ' — no date'}\n\n"
            f"Lines to translate, keeping each id:\n{listing}"
        )
        data = await self._json(NARRATION_SYSTEM, prompt, NARRATION_SCHEMA, 0.2)
        if data is None:
            return None

        wanted = {str(n.get("id")) for n in nodes}
        out: list[dict] = []
        for raw in data.get("nodes", []):
            node_id = str(raw.get("id", ""))
            text = str(raw.get("text", "")).strip()
            if node_id not in wanted or not text:
                continue
            verdict = guard.check_outbound(text, plan, plan.evidence, ledger)
            out.append(
                {
                    "id": node_id,
                    "text": text if verdict.allowed else "",
                    "held": not verdict.allowed,
                    "reason": verdict.reason,
                    "language": patient.language.value,
                }
            )
        return out


__all__ = ["GroqActors"]
