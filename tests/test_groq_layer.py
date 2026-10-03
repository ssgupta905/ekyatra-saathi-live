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


def test_a_rate_limit_is_not_retried(ledger_and_plan):
    """Not transient in a way an immediate second call fixes, and hammering a
    rate limit makes it worse."""
    ledger, plan = ledger_and_plan
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

    assert len(client.chat.completions.calls) == 1
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
