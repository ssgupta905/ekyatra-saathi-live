"""Claude as a bounded language layer.

Claude does exactly one job in Saathi: turn a `VisitPlan` that deterministic
code already decided into a short message a frightened, tired caregiver can act
on, in their language. It does not decide whether to travel, it does not read
reports, and it does not answer questions.

Everything that binds the output — the system prompt, the response schema, the
cross-checks and the guard — is in `rendering.py` and shared with every other
backend. This module is only how to reach Anthropic.
"""

from __future__ import annotations

import json
import logging

import anthropic
from pydantic import ValidationError

from ..domain.enums import Channel, Language
from ..domain.models import CaregiverMessage, VisitPlan
from ..ledger.evidence import InMemoryEvidenceLedger
from .rendering import (
    LANGUAGE_NAMES,
    MAX_TOKENS,
    RESPONSE_SCHEMA,
    SYSTEM_PROMPT,
    LanguageLayerError,
    RenderedMessage,
    accept,
    divert,
    plan_brief,
    user_prompt,
)

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5"

__all__ = [
    "LANGUAGE_NAMES",
    "MAX_TOKENS",
    "MODEL",
    "RESPONSE_SCHEMA",
    "SYSTEM_PROMPT",
    "ClaudeLanguageLayer",
    "LanguageLayerError",
    "RenderedMessage",
    "plan_brief",
]


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

    def describe(self) -> str:
        return f"Claude · {self._model}"

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

        def diverted(reason: str) -> CaregiverMessage:
            return divert(plan, language, channel, plan.evidence, reason)

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_prompt(plan, language, channel, ledger)}
                ],
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

        return accept(rendered, plan, language, channel, ledger)
