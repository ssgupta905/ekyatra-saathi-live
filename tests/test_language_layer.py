"""The language layer must fail closed.

These run without network: the Anthropic client is stubbed, so what is under
test is the binding between the model's output and the plan — which is the part
that protects the family, and the part that must keep working when the model
does something unexpected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

import anthropic
import pytest
from saathi.domain.enums import Channel, Decision, Language, SourceSystem, StepKind, StepStatus
from saathi.domain.models import BlockedPrerequisite, VisitPlan
from saathi.language.claude import ClaudeLanguageLayer
from saathi.ledger.evidence import InMemoryEvidenceLedger


@dataclass
class _Block:
    text: str
    type: str = "text"


@dataclass
class _Response:
    content: list
    stop_reason: str = "end_turn"
    stop_details: object = None


class _StubMessages:
    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self._response


class _StubClient:
    def __init__(self, response=None, raises=None):
        self.messages = _StubMessages(response, raises)


def _payload(body, decision="go", mentions_date=True):
    return _Response(
        content=[
            _Block(
                json.dumps(
                    {
                        "body": body,
                        "english_gloss": body,
                        "restates_decision": decision,
                        "mentions_date": mentions_date,
                    }
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


def _render(client, plan, ledger):
    layer = ClaudeLanguageLayer(client=client)
    return layer.render(plan, Language.BENGALI, Channel.WHATSAPP, ledger)


def test_clean_render_is_sent(ledger_and_plan):
    ledger, plan = ledger_and_plan
    client = _StubClient(_payload("Report ready. Please come on 12/3."))
    message = _render(client, plan, ledger)

    assert message.routed_to_care_team is False
    assert "12/3" in message.body
    assert message.evidence == plan.evidence


def test_model_is_given_no_tools(ledger_and_plan):
    """There is nothing for a prompt injection to call."""
    ledger, plan = ledger_and_plan
    client = _StubClient(_payload("Report ready. Please come on 12/3."))
    _render(client, plan, ledger)

    assert "tools" not in client.messages.calls[0]


def test_wrong_date_from_the_model_is_diverted(ledger_and_plan):
    ledger, plan = ledger_and_plan
    client = _StubClient(_payload("Please come on 19/3."))
    message = _render(client, plan, ledger)

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
    message = _render(client, wait_plan, ledger)

    assert message.routed_to_care_team is True


def test_decision_mismatch_is_diverted(ledger_and_plan):
    ledger, plan = ledger_and_plan
    client = _StubClient(_payload("Please come on 12/3.", decision="wait"))
    message = _render(client, plan, ledger)

    assert message.routed_to_care_team is True
    assert "does not match" in message.routing_reason


def test_clinical_language_is_diverted(ledger_and_plan):
    ledger, plan = ledger_and_plan
    client = _StubClient(_payload("The biopsy result is negative. Come on 12/3."))
    message = _render(client, plan, ledger)

    assert message.routed_to_care_team is True


def test_unparseable_output_is_diverted(ledger_and_plan):
    ledger, plan = ledger_and_plan
    client = _StubClient(_Response(content=[_Block("not json at all")]))
    message = _render(client, plan, ledger)

    assert message.routed_to_care_team is True
    assert "unparseable" in message.routing_reason


def test_refusal_is_routed_to_a_human_not_retried(ledger_and_plan):
    ledger, plan = ledger_and_plan
    client = _StubClient(_Response(content=[], stop_reason="refusal"))
    message = _render(client, plan, ledger)

    assert message.routed_to_care_team is True
    assert "declined" in message.routing_reason


def test_connection_error_is_diverted_not_raised(ledger_and_plan):
    ledger, plan = ledger_and_plan
    client = _StubClient(raises=anthropic.APIConnectionError(request=None))
    message = _render(client, plan, ledger)

    assert message.routed_to_care_team is True
    assert message.body == ""
