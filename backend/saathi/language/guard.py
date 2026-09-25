"""The clinical guard.

Saathi is a logistics system. It must never diagnose, interpret a report, score
risk, or answer a clinical question — it routes those to the care team. The
guard is the enforcement point, and it runs on two sides:

* `screen_inbound`  — a caregiver's message asking something clinical is
  routed to a human, never answered.
* `check_outbound`  — the text Claude produced is checked against the plan it
  was supposed to render, and against a prohibited-content list, before it can
  reach a family.

The guard is deliberately dumb and deterministic. It is the last thing between
a language model and a frightened family, so it is built to be read and audited
by a clinician, not to be clever.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from ..domain.enums import Decision
from ..domain.models import CaregiverMessage, EvidenceRef, VisitPlan
from ..ledger.evidence import InMemoryEvidenceLedger

#: Words that signal a clinical question or a clinical claim. Matched
#: case-insensitively on word boundaries. Multilingual terms are included
#: because caregivers write in transliterated Hindi/Bengali/Odia constantly.
CLINICAL_TERMS: tuple[str, ...] = (
    # Diagnosis / staging / prognosis
    "diagnos", "prognos", "stage", "staging", "metasta", "malignan", "benign",
    "tumour", "tumor", "carcinoma", "sarcoma", "lesion", "grade",
    "remission", "relapse", "recurrence", "spread", "survival", "curable",
    # Treatment decisions
    "chemo", "radiation", "radiotherapy", "surgery", "operable", "dose",
    "dosage", "medicine", "medication", "drug", "tablet", "prescri",
    "side effect", "treatment plan",
    # Result interpretation
    "result mean", "report mean", "positive", "negative", "normal range",
    "abnormal", "biopsy said", "what does the report",
    # Transliterated / vernacular
    "kya hoga", "theek ho", "ilaj", "dawa", "bimari", "cancer hai",
    "bhalo hobe", "chikitsa", "osudh", "rog",
)

#: Phrases a Saathi message may never contain, regardless of evidence. These
#: are promises and reassurances the system has no standing to make.
PROHIBITED_PHRASES: tuple[str, ...] = (
    "you will be fine", "don't worry", "do not worry", "nothing to worry",
    "it looks good", "looks normal", "good news", "bad news",
    "the doctor thinks", "in my opinion", "i recommend", "you should take",
)

#: A message that promises a date must have come from a GO plan.
DATE_PROMISE = re.compile(
    r"\b(come|travel|reach|visit|aaiye|aayen|asun|ashben)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GuardVerdict:
    allowed: bool
    reason: str | None = None
    #: Terms that triggered a block, for the navigator console and audit log.
    triggers: tuple[str, ...] = ()

    def __bool__(self) -> bool:  # convenience in `if verdict:` checks
        return self.allowed


def _matches(text: str, terms: Iterable[str]) -> tuple[str, ...]:
    lowered = text.lower()
    return tuple(term for term in terms if term in lowered)


def screen_inbound(text: str) -> GuardVerdict:
    """Decide whether a caregiver's message is answerable by Saathi at all.

    Anything clinical is not. `allowed=False` means "route to the care team",
    which is a success, not an error.
    """
    triggers = _matches(text, CLINICAL_TERMS)
    if triggers:
        return GuardVerdict(
            allowed=False,
            reason="clinical question — routed to care team",
            triggers=triggers,
        )
    return GuardVerdict(allowed=True)


def check_outbound(
    body: str,
    plan: VisitPlan,
    evidence: tuple[EvidenceRef, ...],
    ledger: InMemoryEvidenceLedger,
) -> GuardVerdict:
    """Validate rendered text against the plan that authorised it."""
    clinical = _matches(body, CLINICAL_TERMS)
    if clinical:
        return GuardVerdict(
            allowed=False,
            reason="generated text contains clinical language",
            triggers=clinical,
        )

    prohibited = _matches(body, PROHIBITED_PHRASES)
    if prohibited:
        return GuardVerdict(
            allowed=False,
            reason="generated text contains a prohibited reassurance",
            triggers=prohibited,
        )

    if not evidence:
        return GuardVerdict(allowed=False, reason="message carries no evidence refs")

    if not ledger.resolve_all(evidence):
        return GuardVerdict(
            allowed=False, reason="evidence ref does not resolve to a ledger entry"
        )

    # The central invariant: only a GO plan may tell a family to travel.
    if plan.decision is not Decision.GO and DATE_PROMISE.search(body):
        return GuardVerdict(
            allowed=False,
            reason=f"travel instruction in a {plan.decision.value} plan",
        )

    # A GO plan must name a date, and that date must be the planned one.
    if plan.decision is Decision.GO:
        if plan.travel_on is None:
            return GuardVerdict(allowed=False, reason="GO plan without a travel date")
        stated_dates = re.findall(r"\b(\d{1,2})[/-](\d{1,2})\b", body)
        for day, month in stated_dates:
            if (int(day), int(month)) != (plan.travel_on.day, plan.travel_on.month):
                return GuardVerdict(
                    allowed=False,
                    reason="message states a date other than the planned travel date",
                    triggers=(f"{day}/{month}",),
                )

    return GuardVerdict(allowed=True)


def divert(message: CaregiverMessage, reason: str) -> CaregiverMessage:
    """Turn a blocked message into a care-team routing record."""
    return message.model_copy(
        update={"routed_to_care_team": True, "routing_reason": reason}
    )
