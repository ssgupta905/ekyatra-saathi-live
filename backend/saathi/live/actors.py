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

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import groq

from ..domain.enums import StepStatus
from ..domain.models import CareStep, Patient
from ..language import guard
from ..language.rendering import LANGUAGE_NAMES
from ..ledger.evidence import InMemoryEvidenceLedger
from .world import LiveWorld

logger = logging.getLogger(__name__)

MODEL = "openai/gpt-oss-120b"


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
        self, system: str, prompt: str, response_format: dict, temperature: float = 0.6
    ) -> dict[str, Any] | None:
        """One structured call. Returns None on anything that is not clean JSON."""
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format=response_format,
            )
            text = response.choices[0].message.content
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
        ledger: InMemoryEvidenceLedger,
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

    # ---------------- d. trace narration ----------------

    async def narrate_trace(
        self,
        nodes: list[dict],
        patient: Patient,
        plan_run: Any | None,
        ledger: InMemoryEvidenceLedger,
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
