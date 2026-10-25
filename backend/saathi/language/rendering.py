"""What every language backend is bound by.

Saathi can render a plan through Claude or through Groq. The choice must not
change what a family can be told, so everything that constrains the output —
the system prompt, the response schema, the cross-checks against the plan, and
the guard call — lives here and is shared verbatim. A backend module contributes
exactly one thing: how to reach its API.

The binding is structural, not instructional:

1. The prompt contains the plan and the evidence claims. Nothing else. There is
   no tool that can fetch a report, so there is nothing to leak.
2. The response is constrained to a JSON schema whose fields map one-to-one
   onto the plan's fields.
3. `accept()` re-validates the rendered text against the plan afterwards, so a
   prompt injection that survived 1 and 2 still cannot send a family on a
   wasted trip.

Layer 3 is what actually protects the family. Layers 1 and 2 just make layer 3
fire rarely.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ..domain.enums import Channel, Decision, Language
from ..domain.models import CaregiverMessage, EvidenceRef, VisitPlan
from ..ports.ledger import EvidenceLedger
from . import guard

logger = logging.getLogger(__name__)

#: Caregiver messages are short by design — a WhatsApp message or a 30-second
#: voice script. This is a deliberate cap, not a cost-saving guess.
MAX_TOKENS = 2048

LANGUAGE_NAMES = {
    Language.HINDI: "Hindi",
    Language.BENGALI: "Bengali",
    Language.ODIA: "Odia",
    Language.ENGLISH: "English",
}

SYSTEM_PROMPT = """\
You write short logistics messages for families travelling long distances for \
cancer treatment. You are not a clinician and you are not a chatbot.

You will be given a decision that has already been made by a planning system, \
along with the facts that justify it. Your only job is to express that decision \
in the family's language, clearly and kindly.

Rules, in order of importance:

1. Say only what the plan says. Do not add, infer, soften, or extrapolate. If \
the plan does not give a date, do not imply one ("soon", "in a few days", \
"shortly" are all forbidden).
2. Never mention anything clinical: no diagnosis, no staging, no treatment, no \
what a report might say, no reassurance about the illness. You are told only \
whether a report is *ready*, never what is in it.
3. Never say a variant of "don't worry" or "good news". You do not know, and it \
is not your place.
4. Write for someone who may be exhausted, may have limited literacy, and is \
managing money they do not have. Short sentences. Concrete nouns. No hospital \
jargon, no English loanwords where a common word exists.
5. If the decision is to wait, make clear that staying home is the right action \
right now, and that they will be told when to come.
6. When the plan gives a travel date, write it as the day number followed by the \
month name in the family's language — "3 October", "3 अक्टूबर", "৩ অক্টোবর". Never \
a weekday alone, never "tomorrow", never a date other than the one in the plan. \
The guard checks this date against the plan and holds the message if it does \
not match or cannot be read.

Write the message body in the requested language. Keep the reasoning field in \
English — it is for the navigator's audit log, not for the family.
"""

#: Response schema. Mirrors the plan's fields so a divergence is detectable.
#: Every property required and `additionalProperties: false` throughout, which
#: is also exactly what Groq's strict structured-output mode demands.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "body": {
            "type": "string",
            "description": "The message to send, in the requested language.",
        },
        "english_gloss": {
            "type": "string",
            "description": "Literal English translation of body, for the audit log.",
        },
        "restates_decision": {
            "type": "string",
            "enum": ["go", "wait", "uncertain"],
            "description": "The decision the body communicates. Must match the plan.",
        },
        "mentions_date": {
            "type": "boolean",
            "description": "True only if body states a specific travel date.",
        },
    },
    "required": ["body", "english_gloss", "restates_decision", "mentions_date"],
    "additionalProperties": False,
}


class RenderedMessage(BaseModel):
    body: str
    english_gloss: str
    restates_decision: Decision
    mentions_date: bool = Field(
        description="Self-report used as a cross-check against the plan."
    )


class LanguageLayerError(RuntimeError):
    """Raised when rendering failed in a way the caller must handle."""


def plan_brief(plan: VisitPlan, ledger: EvidenceLedger) -> str:
    """Render the plan as the only context the model receives."""
    lines = [f"DECISION: {plan.decision.value}"]

    if plan.decision is Decision.GO:
        lines.append(f"TRAVEL ON: {plan.travel_on.isoformat()} ({plan.travel_on:%A %d %B})")
        if plan.bundled_step_ids:
            lines.append("STEPS IN THIS ONE TRIP: " + ", ".join(plan.bundled_step_ids))
        if plan.where_to_go_first:
            lines.append(f"GO FIRST TO: {plan.where_to_go_first}")
        if plan.what_to_bring:
            lines.append("BRING: " + ", ".join(plan.what_to_bring))
    elif plan.decision is Decision.WAIT:
        lines.append("TRAVEL ON: not yet — do not state or imply any date")
        for blocked in plan.blocked_by:
            lines.append(
                f"WAITING ON: {blocked.kind.value} (status: {blocked.status.value})"
            )
    else:
        lines.append(
            "TRAVEL ON: unknown — say plainly that there is no date yet and "
            "that they will be contacted. Promise nothing."
        )

    claims = []
    for ref in plan.evidence:
        entry = ledger.get(ref.ledger_id)
        if entry is not None:
            claims.append(f"- {entry.claim} (source: {entry.source.value})")
    if claims:
        lines.append("FACTS YOU MAY RELY ON:")
        lines.extend(claims)

    return "\n".join(lines)


def user_prompt(
    plan: VisitPlan,
    language: Language,
    channel: Channel,
    ledger: EvidenceLedger,
) -> str:
    voice_note = (
        " (this will be read aloud by a voice system)" if channel is Channel.IVR else ""
    )
    return (
        f"Language: {LANGUAGE_NAMES[language]}\n"
        f"Channel: {channel.value}{voice_note}\n\n"
        f"{plan_brief(plan, ledger)}"
    )


def divert(
    plan: VisitPlan,
    language: Language,
    channel: Channel,
    evidence: tuple[EvidenceRef, ...],
    reason: str,
) -> CaregiverMessage:
    """The only failure mode. Saathi never sends what it could not validate."""
    logger.warning("message diverted for %s: %s", plan.patient_id, reason)
    return CaregiverMessage(
        patient_id=plan.patient_id,
        language=language,
        channel=channel,
        body="",
        evidence=evidence,
        routed_to_care_team=True,
        routing_reason=reason,
    )


def accept(
    rendered: RenderedMessage,
    plan: VisitPlan,
    language: Language,
    channel: Channel,
    ledger: EvidenceLedger,
) -> CaregiverMessage:
    """Cross-check a rendered message against the plan, then guard it.

    Shared by every backend on purpose: if the checks lived in each one, a
    divergence could hide in whichever is less used.
    """
    evidence: tuple[EvidenceRef, ...] = plan.evidence

    if rendered.restates_decision is not plan.decision:
        return divert(
            plan,
            language,
            channel,
            evidence,
            f"rendered decision {rendered.restates_decision.value} "
            f"does not match plan {plan.decision.value}",
        )
    if rendered.mentions_date and plan.decision is not Decision.GO:
        return divert(plan, language, channel, evidence, "date stated in a non-GO plan")

    verdict = guard.check_outbound(rendered.body, plan, evidence, ledger)
    if not verdict.allowed:
        return divert(
            plan,
            language,
            channel,
            evidence,
            verdict.reason or "blocked by clinical guard",
        )

    return CaregiverMessage(
        patient_id=plan.patient_id,
        language=language,
        channel=channel,
        body=rendered.body,
        evidence=evidence,
    )
