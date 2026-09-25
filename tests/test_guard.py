"""The guard is the last thing between a language model and a family."""

from __future__ import annotations

from datetime import date

import pytest
from saathi.domain.enums import Decision, SourceSystem, StepKind, StepStatus
from saathi.domain.models import BlockedPrerequisite, VisitPlan
from saathi.language import guard
from saathi.ledger.evidence import InMemoryEvidenceLedger


@pytest.fixture
def ledger_and_ref():
    ledger = InMemoryEvidenceLedger()
    entry = ledger.record(
        patient_id="P0001",
        source=SourceSystem.ABDM,
        source_record_id="DiagnosticReport/1",
        claim="pathology_report is result_available",
    )
    return ledger, (entry.ref(),)


def _go_plan(travel_on=date(2026, 3, 12)):
    return VisitPlan(
        patient_id="P0001",
        target_step_id="P0001-review",
        decision=Decision.GO,
        travel_on=travel_on,
    )


def _wait_plan():
    return VisitPlan(
        patient_id="P0001",
        target_step_id="P0001-review",
        decision=Decision.WAIT,
        blocked_by=(
            BlockedPrerequisite(
                step_id="P0001-pathology_report",
                kind=StepKind.PATHOLOGY_REPORT,
                status=StepStatus.PENDING_RESULT,
            ),
        ),
    )


# --- inbound screening ---

@pytest.mark.parametrize(
    "text",
    [
        "What does the biopsy report mean?",
        "Is the cancer curable doctor?",
        "Should we start chemo now?",
        "Amar baba bhalo hobe to?",
        "kya hoga ab",
    ],
)
def test_clinical_questions_are_routed_not_answered(text):
    verdict = guard.screen_inbound(text)
    assert verdict.allowed is False
    assert verdict.triggers


@pytest.mark.parametrize(
    "text",
    [
        "Ok we will come on Thursday",
        "Which counter should we go to first?",
        "We missed the bus, can we come the next day?",
        "Thik ache, ami ashbo",
    ],
)
def test_logistics_questions_are_answerable(text):
    assert guard.screen_inbound(text).allowed is True


# --- outbound checking ---

def test_clean_go_message_passes(ledger_and_ref):
    ledger, refs = ledger_and_ref
    body = "The report is ready. Please come on 12/3. Go first to the OPD counter."
    assert guard.check_outbound(body, _go_plan(), refs, ledger).allowed is True


def test_travel_instruction_in_a_wait_plan_is_blocked(ledger_and_ref):
    """The failure that costs a family a 1,900 km round trip."""
    ledger, refs = ledger_and_ref
    body = "Please come to the hospital on Thursday."
    verdict = guard.check_outbound(body, _wait_plan(), refs, ledger)
    assert verdict.allowed is False
    assert "wait" in (verdict.reason or "")


def test_wrong_date_is_blocked(ledger_and_ref):
    ledger, refs = ledger_and_ref
    body = "Please come on 15/3."
    verdict = guard.check_outbound(body, _go_plan(date(2026, 3, 12)), refs, ledger)
    assert verdict.allowed is False
    assert "date" in (verdict.reason or "")


def test_clinical_language_in_generated_text_is_blocked(ledger_and_ref):
    ledger, refs = ledger_and_ref
    body = "Your biopsy report is ready and the result is negative. Come on 12/3."
    assert guard.check_outbound(body, _go_plan(), refs, ledger).allowed is False


def test_reassurance_is_blocked(ledger_and_ref):
    ledger, refs = ledger_and_ref
    body = "The report is ready, don't worry. Come on 12/3."
    verdict = guard.check_outbound(body, _go_plan(), refs, ledger)
    assert verdict.allowed is False
    assert "reassurance" in (verdict.reason or "")


def test_message_without_evidence_is_blocked(ledger_and_ref):
    ledger, _ = ledger_and_ref
    verdict = guard.check_outbound("Come on 12/3.", _go_plan(), (), ledger)
    assert verdict.allowed is False


def test_message_with_unresolvable_evidence_is_blocked(ledger_and_ref):
    ledger, refs = ledger_and_ref
    forged = refs[0].model_copy(update={"ledger_id": "does-not-exist"})
    verdict = guard.check_outbound("Come on 12/3.", _go_plan(), (forged,), ledger)
    assert verdict.allowed is False
