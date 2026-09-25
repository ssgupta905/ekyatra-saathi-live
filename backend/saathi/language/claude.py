"""Claude as a bounded language layer.

Claude does exactly one job in Saathi: turn a `VisitPlan` that deterministic
code already decided into a short message a frightened, tired caregiver can act
on, in their language. It does not decide whether to travel, it does not read
reports, and it does not answer questions.

The binding is structural, not just instructional:

1. The prompt contains the plan and the evidence claims. Nothing else. There is
   no tool that can fetch a report, so there is nothing to leak.
2. The response is constrained to a JSON schema whose fields map one-to-one
   onto the plan's fields.
3. `guard.check_outbound` re-validates the rendered text against the plan
   afterwards, so a prompt injection that survived 1 and 2 still cannot send a
   family on a wasted trip.

Layer 3 is what actually protects the family. Layers 1 and 2 just make layer 3
fire rarely.
"""

from __future__ import annotations

import json
import logging

import anthropic
from pydantic import BaseModel, Field, ValidationError

from ..domain.enums import Channel, Decision, Language
from ..domain.models import CaregiverMessage, EvidenceRef, VisitPlan
from ..ledger.evidence import InMemoryEvidenceLedger
from . import guard

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5"

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

Write the message body in the requested language. Keep the reasoning field in \
English — it is for the navigator's audit log, not for the family.
"""

#: Response schema. Mirrors the plan's fields so a divergence is detectable.
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


def _plan_brief(plan: VisitPlan, ledger: InMemoryEvidenceLedger) -> str:
    """Render the plan as the only context Claude receives."""
    lines = [f"DECISION: {plan.decision.value}"]

    if plan.decision is Decision.GO:
        lines.append(f"TRAVEL ON: {plan.travel_on.isoformat()} ({plan.travel_on:%A %d %B})")
        if plan.bundled_step_ids:
            lines.append(
                "STEPS IN THIS ONE TRIP: " + ", ".join(plan.bundled_step_ids)
            )
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


class ClaudeLanguageLayer:
    """Renders plans into caregiver messages. Fails closed."""

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        model: str = MODEL,
    ) -> None:
        # Zero-arg client resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or
        # an `ant auth login` profile, in that order.
        self._client = client or anthropic.Anthropic()
        self._model = model

    def render(
        self,
        plan: VisitPlan,
        language: Language,
        channel: Channel,
        ledger: InMemoryEvidenceLedger,
    ) -> CaregiverMessage:
        """Render `plan` into a guarded `CaregiverMessage`.

        On any failure — API error, schema violation, refusal, or a guard
        rejection — returns a message flagged `routed_to_care_team`. Saathi
        never falls back to sending something it could not validate.
        """
        evidence: tuple[EvidenceRef, ...] = plan.evidence

        def diverted(reason: str) -> CaregiverMessage:
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

        voice_note = (
            " (this will be read aloud by a voice system)"
            if channel is Channel.IVR
            else ""
        )
        prompt = (
            f"Language: {LANGUAGE_NAMES[language]}\n"
            f"Channel: {channel.value}{voice_note}\n\n"
            f"{_plan_brief(plan, ledger)}"
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                thinking={"type": "adaptive"},
                output_config={
                    # Rendering a fixed plan into one language is not a hard
                    # reasoning task; low effort keeps latency down for IVR.
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA},
                },
            )
        except anthropic.NotFoundError as exc:
            return diverted(f"model or endpoint not found: {exc}")
        except anthropic.RateLimitError:
            return diverted("rate limited — retry queued")
        except anthropic.APIStatusError as exc:
            return diverted(f"api error {exc.status_code}")
        except anthropic.APIConnectionError:
            return diverted("could not reach the language service")

        # A refusal here is not an error to route around with another model:
        # something about this case warrants a human, so send it to one.
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            return diverted(f"language model declined ({category})")

        try:
            text = next(b.text for b in response.content if b.type == "text")
            rendered = RenderedMessage.model_validate(json.loads(text))
        except (StopIteration, json.JSONDecodeError, ValidationError) as exc:
            return diverted(f"unparseable model output: {exc}")

        # Cross-check the model's own account of what it wrote against the plan.
        if rendered.restates_decision is not plan.decision:
            return diverted(
                f"rendered decision {rendered.restates_decision.value} "
                f"does not match plan {plan.decision.value}"
            )
        if rendered.mentions_date and plan.decision is not Decision.GO:
            return diverted("date stated in a non-GO plan")

        verdict = guard.check_outbound(rendered.body, plan, evidence, ledger)
        if not verdict.allowed:
            return diverted(verdict.reason or "blocked by clinical guard")

        return CaregiverMessage(
            patient_id=plan.patient_id,
            language=language,
            channel=channel,
            body=rendered.body,
            evidence=evidence,
        )
