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
from ..ports.ledger import EvidenceLedger

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

#: Indic digits, normalised to ASCII before any date is read. "৩ অক্টোবর" is
#: exactly as much a date promise as "3/10", and a guard that can only see Latin
#: digits is blind in the three languages this pilot actually runs in.
_DIGIT_TABLE = {
    ord(indic): ascii_digit
    for group in ("०१२३४५६७८९", "০১২৩৪৫৬৭৮৯", "୦୧୨୩୪୫୬୭୮୯")
    for indic, ascii_digit in zip(group, "0123456789", strict=True)
}

#: Month names the guard can read. Deliberately a plain list rather than a date
#: parser: a clinician or a native speaker can extend it without reading any
#: logic, and a name that is *missing* makes the guard fail closed — it cannot
#: verify the date, so it blocks — which is the safe direction to be wrong in.
MONTH_NAMES: tuple[tuple[int, tuple[str, ...]], ...] = (
    (1, ("january", "jan", "जनवरी", "জানুয়ারি", "ଜାନୁଆରୀ")),
    (2, ("february", "feb", "फरवरी", "ফেব্রুয়ারি", "ଫେବୃଆରୀ")),
    (3, ("march", "mar", "मार्च", "মার্চ", "ମାର୍ଚ୍ଚ")),
    (4, ("april", "apr", "अप्रैल", "এপ্রিল", "ଅପ୍ରେଲ")),
    (5, ("may", "मई", "মে", "ମଇ")),
    (6, ("june", "jun", "जून", "জুন", "ଜୁନ")),
    (7, ("july", "jul", "जुलाई", "জুলাই", "ଜୁଲାଇ")),
    (8, ("august", "aug", "अगस्त", "আগস্ট", "ଅଗଷ୍ଟ")),
    (9, ("september", "sept", "sep", "सितंबर", "सितम्बर", "সেপ্টেম্বর", "ସେପ୍ଟେମ୍ବର")),
    (10, ("october", "oct", "अक्टूबर", "অক্টোবর", "ଅକ୍ଟୋବର")),
    (11, ("november", "nov", "नवंबर", "नवम्बर", "নভেম্বর", "ନଭେମ୍ବର")),
    (12, ("december", "dec", "दिसंबर", "दिसम्बर", "ডিসেম্বর", "ଡିସେମ୍ବର")),
)

_MONTH_LOOKUP = {name: number for number, names in MONTH_NAMES for name in names}
#: Longest first, so "sept" is not swallowed by "sep".
_MONTH_ALTERNATION = "|".join(
    sorted((re.escape(name) for name in _MONTH_LOOKUP), key=len, reverse=True)
)

_NUMERIC_DATE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})\b")
_DAY_THEN_MONTH = re.compile(rf"(\d{{1,2}})[\s,.\-]{{0,3}}({_MONTH_ALTERNATION})")
_MONTH_THEN_DAY = re.compile(rf"({_MONTH_ALTERNATION})[\s,.\-]{{0,3}}(\d{{1,2}})")


def stated_dates(body: str) -> frozenset[tuple[int, int]]:
    """Every (day, month) the message can be read as naming.

    Covers `3/10`, `3 October`, `October 3`, and the same written in Devanagari,
    Bengali or Odia numerals and month names. Anything this cannot read counts
    as *not stated*, which blocks a GO message rather than passing it.
    """
    text = body.translate(_DIGIT_TABLE).lower()
    found: set[tuple[int, int]] = set()

    for day, month in _NUMERIC_DATE.findall(text):
        found.add((int(day), int(month)))
    for day, name in _DAY_THEN_MONTH.findall(text):
        found.add((int(day), _MONTH_LOOKUP[name]))
    for name, day in _MONTH_THEN_DAY.findall(text):
        found.add((int(day), _MONTH_LOOKUP[name]))

    return frozenset(
        (day, month) for day, month in found if 1 <= day <= 31 and 1 <= month <= 12
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


#: Process questions — "what happens to my date/dose/visit" — that have a
#: safe, content-free answer ("the doctor/navigator decides, by when"),
#: distinct from a question that wants a clinical answer. Deliberately
#: narrow and English/Hindi/transliteration-only for now: extending this to
#: Bengali and Odia natively, and getting the boundary right against
#: `CLINICAL_TERMS`, is the same clinician-vocabulary judgement call the
#: README's Known Gap #1 defers for the inbound clinical guard — this is a
#: starter set, not a finished one.
PROCESS_QUESTION_PATTERNS: tuple[str, ...] = (
    "what happens to", "what about my", "kya hoga mera", "mera kya hoga",
    "when will i know", "kab pata chalega", "is it still happening",
    "will it still happen", "what happens now",
)


class InboundCategory:
    CLINICAL = "clinical"
    PROCESS = "process"
    OTHER = "other"


#: "dose 13" names which cycle of a maintenance schedule, not a clinical
#: amount — without this, every maintenance process question would trip the
#: generic "dose"/"dosage" clinical term and never reach a process answer.
_DOSE_NUMBER = re.compile(r"\bdose\s*#?\s*\d+\b", re.IGNORECASE)


def classify_inbound(text: str) -> str:
    """Which of the three shapes an inbound message is.

    Checked in this order on purpose: a question that is *both* process- and
    clinical-shaped ("what happens to my diagnosis") must be routed as
    clinical, never answered — `screen_inbound`'s existing behaviour is
    unchanged by this function; this only adds a second classification
    alongside it.
    """
    clinical_hits = set(_matches(text, CLINICAL_TERMS))
    if _DOSE_NUMBER.search(text):
        clinical_hits -= {"dose", "dosage"}
    if clinical_hits:
        return InboundCategory.CLINICAL
    if _matches(text, PROCESS_QUESTION_PATTERNS):
        return InboundCategory.PROCESS
    return InboundCategory.OTHER


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
    ledger: EvidenceLedger,
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

        planned = (plan.travel_on.day, plan.travel_on.month)
        stated = stated_dates(body)

        wrong = stated - {planned}
        if wrong:
            return GuardVerdict(
                allowed=False,
                reason="message states a date other than the planned travel date",
                triggers=tuple(f"{day}/{month}" for day, month in sorted(wrong)),
            )
        if planned not in stated:
            # Absence of a readable date is not evidence of a correct one. A
            # message whose date the guard cannot check is one a person should
            # send — this used to pass, and a model writing the date in words or
            # in Bengali numerals could put a family on a bus a day early.
            return GuardVerdict(
                allowed=False,
                reason=(
                    "message does not state the planned travel date in a form the "
                    "guard can read"
                ),
            )

    return GuardVerdict(allowed=True)


def divert(message: CaregiverMessage, reason: str) -> CaregiverMessage:
    """Turn a blocked message into a care-team routing record."""
    return message.model_copy(
        update={"routed_to_care_team": True, "routing_reason": reason}
    )
