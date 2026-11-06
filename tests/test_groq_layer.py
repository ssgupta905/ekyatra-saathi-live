"""The Groq layer must fail closed, exactly as the Claude layer does.

Speed is the reason Groq is in this project, and speed is a reason to be
suspicious of it: a fast wrong message is still a wrong message. These are the
same checks as `test_language_layer.py`, run against the other backend, because
the moment the two diverge is the moment the weaker one becomes the attack.

No network: the client is stubbed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

import groq
import httpx
import pytest
from saathi.domain.enums import Channel, Decision, Language, SourceSystem, StepKind, StepStatus
from saathi.domain.models import BlockedPrerequisite, VisitPlan
from saathi.language.groq_layer import GroqLanguageLayer
from saathi.ledger.evidence import InMemoryEvidenceLedger


@dataclass
class _Message:
    content: str | None


@dataclass
class _Choice:
    message: _Message
    finish_reason: str = "stop"


@dataclass
class _Response:
    choices: list = field(default_factory=list)


class _StubCompletions:
    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self._response


class _StubClient:
    def __init__(self, response=None, raises=None):
        self.chat = type("_Chat", (), {})()
        self.chat.completions = _StubCompletions(response, raises)


def _payload(body, decision="go", mentions_date=True):
    return _Response(
        choices=[
            _Choice(
                _Message(
                    json.dumps(
                        {
                            "body": body,
                            "english_gloss": body,
                            "restates_decision": decision,
                            "mentions_date": mentions_date,
                        }
                    )
                )
            )
        ]
    )


@pytest.fixture
def ledger_and_plan():
    ledger = InMemoryEvidenceLedger()
    entry = ledger.record(
        patient_id="P0001",
        source=SourceSystem.ABDM,
        source_record_id="P0001-pathology_report",
        claim="pathology_report is result_available",
    )
    plan = VisitPlan(
        patient_id="P0001",
        target_step_id="P0001-review",
        decision=Decision.GO,
        travel_on=date(2026, 3, 12),
        evidence=(entry.ref(),),
    )
    return ledger, plan


def _render(client, plan, ledger, language=Language.HINDI):
    layer = GroqLanguageLayer(client=client)
    return layer.render(plan, language, Channel.WHATSAPP, ledger)


def test_clean_render_is_sent(ledger_and_plan):
    ledger, plan = ledger_and_plan
    message = _render(_StubClient(_payload("Report ready. Please come on 12/3.")), plan, ledger)

    assert message.routed_to_care_team is False
    assert "12/3" in message.body
    assert message.evidence == plan.evidence


def test_the_model_is_given_no_tools(ledger_and_plan):
    """There is nothing for a prompt injection to call."""
    ledger, plan = ledger_and_plan
    client = _StubClient(_payload("Report ready. Please come on 12/3."))
    _render(client, plan, ledger)

    call = client.chat.completions.calls[0]
    assert "tools" not in call
    assert "tool_choice" not in call


def test_the_schema_is_sent_strict(ledger_and_plan):
    """Best-effort JSON would let a malformed shape through to the parser."""
    ledger, plan = ledger_and_plan
    client = _StubClient(_payload("Report ready. Please come on 12/3."))
    _render(client, plan, ledger)

    schema = client.chat.completions.calls[0]["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert set(schema["schema"]["required"]) == set(schema["schema"]["properties"])


def test_wrong_date_from_the_model_is_diverted(ledger_and_plan):
    ledger, plan = ledger_and_plan
    message = _render(_StubClient(_payload("Please come on 19/3.")), plan, ledger)

    assert message.routed_to_care_team is True
    assert message.body == ""


def test_travel_instruction_under_a_wait_plan_is_diverted(ledger_and_plan):
    """The injection that matters: a WAIT plan must never become a trip."""
    ledger, plan = ledger_and_plan
    wait_plan = plan.model_copy(
        update={
            "decision": Decision.WAIT,
            "travel_on": None,
            "blocked_by": (
                BlockedPrerequisite(
                    step_id="P0001-pathology_report",
                    kind=StepKind.PATHOLOGY_REPORT,
                    status=StepStatus.PENDING_RESULT,
                ),
            ),
        }
    )
    client = _StubClient(
        _payload("Please come to the hospital.", decision="wait", mentions_date=False)
    )
    assert _render(client, wait_plan, ledger).routed_to_care_team is True


def test_decision_mismatch_is_diverted(ledger_and_plan):
    ledger, plan = ledger_and_plan
    message = _render(_StubClient(_payload("Please come on 12/3.", decision="wait")), plan, ledger)

    assert message.routed_to_care_team is True
    assert "does not match" in message.routing_reason


def test_clinical_language_is_diverted(ledger_and_plan):
    ledger, plan = ledger_and_plan
    client = _StubClient(_payload("The biopsy result is negative. Come on 12/3."))
    assert _render(client, plan, ledger).routed_to_care_team is True


def test_unparseable_output_is_diverted(ledger_and_plan):
    ledger, plan = ledger_and_plan
    client = _StubClient(_Response(choices=[_Choice(_Message("not json at all"))]))
    message = _render(client, plan, ledger)

    assert message.routed_to_care_team is True
    assert "unparseable" in message.routing_reason


def test_empty_content_is_diverted(ledger_and_plan):
    ledger, plan = ledger_and_plan
    message = _render(_StubClient(_Response(choices=[_Choice(_Message(None))])), plan, ledger)

    assert message.routed_to_care_team is True
    assert message.body == ""


def test_a_content_filter_goes_to_a_human_not_to_another_model(ledger_and_plan):
    ledger, plan = ledger_and_plan
    filtered = _Response(choices=[_Choice(_Message(None), finish_reason="content_filter")])
    message = _render(_StubClient(filtered), plan, ledger)

    assert message.routed_to_care_team is True
    assert "declined" in message.routing_reason


def test_connection_error_is_diverted_not_raised(ledger_and_plan):
    ledger, plan = ledger_and_plan
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    client = _StubClient(raises=groq.APIConnectionError(request=request))
    message = _render(client, plan, ledger)

    assert message.routed_to_care_team is True
    assert message.body == ""


def test_rate_limit_is_diverted(ledger_and_plan):
    ledger, plan = ledger_and_plan
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(429, request=request)
    client = _StubClient(
        raises=groq.RateLimitError("slow down", response=response, body=None)
    )
    message = _render(client, plan, ledger)

    assert message.routed_to_care_team is True
    assert "rate limited" in message.routing_reason


def test_both_backends_are_bound_by_the_same_schema_and_prompt():
    """A divergence here is how the weaker backend becomes the way in."""
    from saathi.language import claude, groq_layer, rendering

    assert claude.SYSTEM_PROMPT is rendering.SYSTEM_PROMPT
    assert claude.RESPONSE_SCHEMA is rendering.RESPONSE_SCHEMA
    assert groq_layer.SYSTEM_PROMPT is rendering.SYSTEM_PROMPT
    assert groq_layer.RESPONSE_FORMAT["json_schema"]["schema"] is rendering.RESPONSE_SCHEMA


# ---------------------------------------------------------------- retries
#
# Constrained decoding occasionally fails to emit schema-valid JSON on a prompt
# it handles fine the rest of the time — observed on roughly one render in
# twenty against the live service, reproducibly on the richest plan. Diverting
# on the first miss costs a family their travel date and buys no safety: the
# guard reads a retry exactly as it reads a first attempt.


def _schema_miss() -> groq.APIStatusError:
    return groq.APIStatusError(
        "bad request",
        response=httpx.Response(400, request=httpx.Request("POST", "http://x")),
        body={"error": {"message": "Failed to generate JSON. Please adjust your prompt."}},
    )


class _FailsThenSucceeds:
    """Fails constrained decoding `failures` times, then renders normally."""

    def __init__(self, failures: int, response) -> None:
        self._failures = failures
        self._response = response
        self.calls: list[dict] = []
        self.chat = type("_Chat", (), {})()
        self.chat.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) <= self._failures:
            raise _schema_miss()
        return self._response


def test_a_schema_miss_is_retried_once(ledger_and_plan):
    ledger, plan = ledger_and_plan
    client = _FailsThenSucceeds(1, _payload("12 मार्च को आइए।"))

    message = GroqLanguageLayer(client=client).render(
        plan, Language.HINDI, Channel.WHATSAPP, ledger
    )

    assert len(client.calls) == 2
    # The retry nudges temperature up: repeating a near-deterministic call that
    # just failed tends to fail the same way.
    assert client.calls[1]["temperature"] > client.calls[0]["temperature"]
    assert message.routed_to_care_team is False


def test_a_second_schema_miss_fails_closed(ledger_and_plan):
    ledger, plan = ledger_and_plan
    client = _FailsThenSucceeds(2, _payload("12 मार्च को आइए।"))

    message = GroqLanguageLayer(client=client).render(
        plan, Language.HINDI, Channel.WHATSAPP, ledger
    )

    assert len(client.calls) == 2, "exactly one retry, never a loop"
    assert message.routed_to_care_team is True
    assert "Failed to generate JSON" in (message.routing_reason or "")


def test_the_retry_sends_the_same_prompt(ledger_and_plan):
    """The second attempt must be the same request, not a softened one.

    A retry that quietly dropped the schema or trimmed the plan would be a
    second, weaker code path producing messages the first path would reject.
    """
    ledger, plan = ledger_and_plan
    client = _FailsThenSucceeds(1, _payload("12 मार्च को आइए।"))

    GroqLanguageLayer(client=client).render(plan, Language.HINDI, Channel.WHATSAPP, ledger)

    first, second = client.calls
    assert first["messages"] == second["messages"]
    assert first["response_format"] == second["response_format"]
    assert first["max_tokens"] == second["max_tokens"]


def test_a_rate_limit_is_retried_after_waiting(ledger_and_plan, monkeypatch):
    """Once, after waiting — not immediately.

    This test used to assert the opposite, on the reasoning that hammering a
    rate limit makes it worse. That reasoning holds for an *immediate* retry
    and not for a patient one: a burst of renders earned forty-six 429s in one
    run, and twenty-two families were simply never written to. Waiting the
    short time the service asks for turns those into late messages instead of
    missing ones."""
    ledger, plan = ledger_and_plan
    monkeypatch.setattr("saathi.language.groq_layer.time.sleep", lambda _: None)
    client = _StubClient(
        raises=groq.RateLimitError(
            "slow down",
            response=httpx.Response(429, request=httpx.Request("POST", "http://x")),
            body=None,
        )
    )

    message = GroqLanguageLayer(client=client).render(
        plan, Language.HINDI, Channel.WHATSAPP, ledger
    )

    assert len(client.chat.completions.calls) == 2, "one wait, then one more try"
    assert message.routed_to_care_team is True


def test_an_unrelated_400_is_not_retried(ledger_and_plan):
    ledger, plan = ledger_and_plan
    client = _StubClient(
        raises=groq.APIStatusError(
            "bad request",
            response=httpx.Response(400, request=httpx.Request("POST", "http://x")),
            body={"error": {"message": "model_not_supported"}},
        )
    )

    message = GroqLanguageLayer(client=client).render(
        plan, Language.HINDI, Channel.WHATSAPP, ledger
    )

    assert len(client.chat.completions.calls) == 1
    assert message.routed_to_care_team is True
    # The service's own words reach the operator rather than a bare status code.
    assert "model_not_supported" in (message.routing_reason or "")


# ---------------------------------------------------------------- rate limits


def _rate_limited(retry_after: str | None = "1") -> groq.RateLimitError:
    headers = {"retry-after": retry_after} if retry_after else {}
    return groq.RateLimitError(
        "slow down",
        response=httpx.Response(
            429, headers=headers, request=httpx.Request("POST", "http://x")
        ),
        body=None,
    )


class _LimitedThenFine:
    """Rate-limits `limits` times, then renders normally."""

    def __init__(self, limits: int, response) -> None:
        self._limits = limits
        self._response = response
        self.calls: list[dict] = []
        self.chat = type("_Chat", (), {})()
        self.chat.completions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) <= self._limits:
            raise _rate_limited()
        return self._response


def test_a_rate_limit_is_waited_out_rather_than_dropped(ledger_and_plan, monkeypatch):
    """The old behaviour said "retry queued" and queued nothing.

    A family waiting to hear whether to travel is not served by a message that
    was composed, refused and silently abandoned. The service says how long;
    waiting that long turns a dropped message into a late one.
    """
    slept: list[float] = []
    monkeypatch.setattr("saathi.language.groq_layer.time.sleep", slept.append)
    ledger, plan = ledger_and_plan
    client = _LimitedThenFine(1, _payload("12 मार्च को आइए।"))

    message = GroqLanguageLayer(client=client).render(
        plan, Language.HINDI, Channel.WHATSAPP, ledger
    )

    assert len(client.calls) == 2
    assert slept == [1.0], "it should wait exactly as long as the service asked"
    assert message.routed_to_care_team is False


def test_it_waits_once_and_then_says_so(ledger_and_plan, monkeypatch):
    monkeypatch.setattr("saathi.language.groq_layer.time.sleep", lambda _: None)
    ledger, plan = ledger_and_plan
    client = _LimitedThenFine(5, _payload("12 मार्च को आइए।"))

    message = GroqLanguageLayer(client=client).render(
        plan, Language.HINDI, Channel.WHATSAPP, ledger
    )

    assert len(client.calls) == 2, "one wait, not a loop that holds up everything behind it"
    assert message.routed_to_care_team is True
    assert "still limited" in (message.routing_reason or "")


def test_an_unreasonable_wait_is_not_waited_for(ledger_and_plan, monkeypatch):
    """A limit that clears in an hour is not worth holding a request open for."""
    slept: list[float] = []
    monkeypatch.setattr("saathi.language.groq_layer.time.sleep", slept.append)
    ledger, plan = ledger_and_plan
    client = _LimitedThenFine(1, _payload("12 मार्च को आइए।"))
    def create(**kwargs):
        client.calls.append(kwargs)
        raise _rate_limited("3600")

    client.chat.completions.create = create

    message = GroqLanguageLayer(client=client).render(
        plan, Language.HINDI, Channel.WHATSAPP, ledger
    )

    assert slept == [], "an hour-long limit is not something to sit and wait out"
    assert message.routed_to_care_team is True


def test_durations_are_read_in_the_notation_the_service_writes_them():
    """Groq writes "787ms", "1.5s", "4h29m16.8s". float() raises on all three.

    That sent every wait down the blind two-second fallback: long enough to
    miss a token bucket that refills in under a second, short enough that two
    dozen renders woke together and exhausted it again.
    """
    from saathi.language.groq_layer import _duration

    assert _duration("787ms") == pytest.approx(0.787)
    assert _duration("1.5s") == pytest.approx(1.5)
    assert _duration("4h29m16.8s") == pytest.approx(16156.8)
    assert _duration("2") == pytest.approx(2.0)
    assert _duration("") is None


def test_the_token_bucket_reset_is_preferred_over_the_daily_one(ledger_and_plan, monkeypatch):
    """Tokens-per-minute is the limit that bites; requests-per-day is not worth
    waiting for, and reading them in the wrong order gives up on both."""
    slept: list[float] = []
    monkeypatch.setattr("saathi.language.groq_layer.time.sleep", slept.append)
    ledger, plan = ledger_and_plan

    class _Limited:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.chat = type("_Chat", (), {})()
            self.chat.completions = self

        def create(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise groq.RateLimitError(
                    "slow down",
                    response=httpx.Response(
                        429,
                        headers={
                            "x-ratelimit-reset-requests": "4h29m16.8s",
                            "x-ratelimit-reset-tokens": "787ms",
                        },
                        request=httpx.Request("POST", "http://x"),
                    ),
                    body=None,
                )
            return _payload("12 मार्च को आइए।")

    client = _Limited()
    message = GroqLanguageLayer(client=client).render(
        plan, Language.HINDI, Channel.WHATSAPP, ledger
    )

    assert slept == [pytest.approx(0.787)], "it should wait for the bucket, not the day"
    assert message.routed_to_care_team is False
