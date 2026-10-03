"""Groq as a bounded language layer.

Structurally identical to `claude.py` — same prompt, same schema, same
cross-checks, same guard, all imported from `rendering.py`. The only thing that
differs is the API, and the latency: constrained decoding at roughly a thousand
tokens a second is what lets the live demo render a family's message inside a
simulated day rather than after it.

Speed is the reason Groq is here, and it is also the reason to be careful: a
fast wrong message is still a wrong message, so nothing about the validation
path is relaxed for it. Every rejection — transport error, unparseable body,
decision mismatch, date under a WAIT plan, guard block — returns a message
routed to the care team, exactly as the Claude layer does.

`strict: true` is deliberate. The shared `RESPONSE_SCHEMA` already marks every
property required with `additionalProperties: false`, which is what constrained
decoding needs, so the model cannot return a shape the parser has to guess at.
It requires a model that supports it (`openai/gpt-oss-20b` and `-120b` do);
pointing `SAATHI_GROQ_MODEL` at one that does not will surface as an API error
and divert, rather than silently falling back to best-effort JSON.
"""

from __future__ import annotations

import json
import logging

import groq
from pydantic import ValidationError

from ..domain.enums import Channel, Language
from ..domain.models import CaregiverMessage, VisitPlan
from ..ledger.evidence import InMemoryEvidenceLedger
from .rendering import (
    MAX_TOKENS,
    RESPONSE_SCHEMA,
    SYSTEM_PROMPT,
    RenderedMessage,
    accept,
    divert,
    user_prompt,
)

logger = logging.getLogger(__name__)

#: Groq models that support `strict: true` constrained decoding.
MODEL = "openai/gpt-oss-20b"

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "caregiver_message",
        "strict": True,
        "schema": RESPONSE_SCHEMA,
    },
}


def _why(exc: groq.APIStatusError) -> str:
    """The service's own explanation, trimmed to something loggable."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            detail = error.get("message") or error.get("code")
            if detail:
                return str(detail)[:300]
    return str(exc)[:300]


def _is_schema_miss(exc: groq.APIStatusError, why: str) -> bool:
    """True when the model simply failed to emit JSON matching the schema.

    Worth one more try, unlike every other 400 here — a malformed request, an
    unsupported parameter or a rejected prompt will fail identically forever.
    """
    return exc.status_code == 400 and "failed to generate json" in why.lower()


class GroqLanguageLayer:
    """Renders plans into caregiver messages, fast. Fails closed."""

    def __init__(
        self,
        client: groq.Groq | None = None,
        api_key: str | None = None,
        model: str = MODEL,
    ) -> None:
        self._client = client or groq.Groq(api_key=api_key)
        self._model = model

    def describe(self) -> str:
        return f"Groq · {self._model}"

    def render(
        self,
        plan: VisitPlan,
        language: Language,
        channel: Channel,
        ledger: InMemoryEvidenceLedger,
    ) -> CaregiverMessage:
        def diverted(reason: str) -> CaregiverMessage:
            return divert(plan, language, channel, plan.evidence, reason)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(plan, language, channel, ledger)},
        ]

        response = None
        # One retry, for one failure mode. Constrained decoding occasionally
        # fails to emit schema-valid JSON on a prompt it handles fine the rest
        # of the time — observed on roughly one render in twenty, reproducibly
        # on the richest plan. The cost of not retrying is a family getting
        # "someone will call you" instead of their travel date, which is a real
        # loss to them and no safer: the guard still reads whatever comes back.
        #
        # Nothing else is retried. A rate limit, a bad model name, or an
        # unreachable service are not transient in a way a second immediate
        # call would fix, and hammering them makes each worse.
        for attempt in range(2):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=MAX_TOKENS,
                    # Rendering a decided plan into one language is not a
                    # creative task. Low temperature keeps the same plan reading
                    # the same way twice, which matters when a navigator reads
                    # it aloud. The retry nudges it up, because repeating a
                    # near-deterministic call that just failed tends to fail the
                    # same way.
                    temperature=0.2 if attempt == 0 else 0.5,
                    messages=messages,
                    response_format=RESPONSE_FORMAT,
                    # No tools, ever. There is nothing for an injection to call.
                )
                break
            except groq.RateLimitError:
                return diverted("rate limited — retry queued")
            except groq.NotFoundError as exc:
                return diverted(f"model or endpoint not found: {exc}")
            except groq.APIStatusError as exc:
                why = _why(exc)
                if attempt == 0 and _is_schema_miss(exc, why):
                    logger.info("retrying a render after a schema miss: %s", why)
                    continue
                # Carry what the service said. "api error 400" tells an operator
                # nothing, and this path is how a message silently stops
                # reaching a family — the one failure that must never be hard
                # to diagnose.
                logger.warning("groq rejected a render: %s %s", exc.status_code, why)
                return diverted(f"api error {exc.status_code}: {why}")
            except groq.APIConnectionError:
                return diverted("could not reach the language service")

        if response is None:  # pragma: no cover — every path above returns
            return diverted("no response from the language service")

        try:
            choice = response.choices[0]
        except (AttributeError, IndexError):
            return diverted("empty response from the language service")

        # Groq surfaces a content filter as a finish reason rather than an
        # error. Treat it the way the Claude layer treats a refusal: something
        # about this case warrants a person, so send it to one.
        if getattr(choice, "finish_reason", None) == "content_filter":
            return diverted("language model declined (content_filter)")

        text = getattr(choice.message, "content", None)
        if not text:
            return diverted("language model returned no text")

        try:
            rendered = RenderedMessage.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as exc:
            return diverted(f"unparseable model output: {exc}")

        return accept(rendered, plan, language, channel, ledger)
