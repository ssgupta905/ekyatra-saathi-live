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
import re
import threading
import time

import groq
from pydantic import ValidationError

from ..domain.enums import Channel, Language
from ..domain.models import CaregiverMessage, VisitPlan
from ..ports.ledger import EvidenceLedger
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


#: The longest a render will wait out a rate limit before giving up. A family
#: hearing late is better than not hearing; a request held much longer than
#: this is holding up everything behind it instead.
RATE_LIMIT_WAIT = 20.0

#: One render at a time. The limit that binds is tokens per minute, and two
#: dozen renders firing together exhaust it, all back off together, and wake
#: together to exhaust it again. Queued, each one waits out its own limit and
#: the queue drains at whatever rate the service will actually sustain.
#: Renders already run on worker threads, so this blocks a thread, never the
#: event loop — the journey chain keeps moving while messages catch up.
_ONE_AT_A_TIME = threading.Lock()


def _retry_after(exc: groq.RateLimitError) -> float | None:
    """How long to wait before one more try, or None for "do not bother".

    Three cases, and they are not the same. The service names a short wait, so
    wait it. The service names an hour, so do not: holding the request open
    changes nothing and blocks everything behind it. The service names nothing,
    so wait a couple of seconds — these bursts usually clear in about that.
    """
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    # Token-per-minute is the limit that actually bites, so read its reset
    # first: it clears in under a second, while the daily request budget reads
    # "4h29m16.8s" and is not worth waiting for.
    for name in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        raw = headers.get(name)
        if not raw:
            continue
        seconds = _duration(str(raw))
        if seconds is None:
            continue
        return seconds if 0 < seconds <= RATE_LIMIT_WAIT else None
    return 2.0


#: Groq writes durations as "787ms", "1.5s" or "4h29m16.8s". A plain float()
#: on any of those raises, which sent every wait down the blind two-second
#: fallback — long enough to miss a bucket that refills in under a second, and
#: short enough that two dozen renders all woke together and exhausted it again.
_DURATION = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m|h)?")
_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, None: 1.0}


def _duration(raw: str) -> float | None:
    """Seconds from a duration the service wrote in its own notation."""
    parts = _DURATION.findall(raw.strip())
    if not parts:
        return None
    return sum(float(value) * _UNITS[unit or None] for value, unit in parts)


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
        ledger: EvidenceLedger,
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
        # A rate limit is retried too, but by waiting rather than by asking
        # again at once. The service says how long; honouring it turns a
        # dropped message into a late one, which for a family waiting to hear
        # whether to travel is not the same thing at all.
        #
        # Nothing else is retried. A bad model name or an unreachable service
        # are not transient in a way a second call would fix.
        waited = False
        for attempt in range(2):
            try:
                with _ONE_AT_A_TIME:
                    response = self._client.chat.completions.create(
                        model=self._model,
                        max_tokens=MAX_TOKENS,
                        # Rendering a decided plan into one language is not a
                        # creative task. Low temperature keeps the same plan
                        # reading the same way twice, which matters when a
                        # navigator reads it aloud. The retry nudges it up,
                        # because repeating a near-deterministic call that just
                        # failed tends to fail the same way.
                        temperature=0.2 if attempt == 0 else 0.5,
                        messages=messages,
                        response_format=RESPONSE_FORMAT,
                        # No tools, ever. Nothing for an injection to call.
                    )
                break
            except groq.RateLimitError as exc:
                pause = _retry_after(exc)
                if waited or pause is None:
                    # Said plainly. The old wording claimed a retry was queued;
                    # nothing queued one, so a family simply never heard.
                    return diverted(f"rate limited, and still limited after {RATE_LIMIT_WAIT}s")
                logger.info("rate limited; waiting %.1fs before one more try", pause)
                time.sleep(pause)
                waited = True
                continue
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
