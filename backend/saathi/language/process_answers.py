"""Process-only answers to an inbound question, phrased in the family's language.

Templated for the same reason `language/holding.py` is: the answer has one
shape — "who decides, by when" — so there is no prose for a model to
hallucinate past. Still routed through `check_outbound`-style evidence
rules: a process answer without a ledger-backed disruption behind it is
refused, not sent.
"""

from __future__ import annotations

from ..domain.enums import Channel, Language
from ..domain.models import CaregiverMessage, EvidenceRef
from ..planner.process_facts import ProcessFact
from .guard import CLINICAL_TERMS, PROHIBITED_PHRASES


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)

_TEMPLATES: dict[Language, str] = {
    Language.HINDI: (
        "Abhi kuch tay nahi hua hai. {awaiting}{by}. "
        "Jaise hi pata chalega, aapko bataya jaayega."
    ),
    Language.BENGALI: "এখনো কিছু ঠিক হয়নি। {awaiting}{by}। জানানো হবে যত তাড়াতাড়ি সম্ভব।",
    Language.ODIA: "ବର୍ତ୍ତମାନ କିଛି ସ୍ଥିର ହୋଇନାହିଁ। {awaiting}{by}। ଶୀଘ୍ର ଜଣାଇ ଦିଆଯିବ।",
    Language.ENGLISH: (
        "Nothing is decided yet. {awaiting}{by}. "
        "You will be told as soon as it is."
    ),
}


def render_process_answer(
    fact: ProcessFact,
    patient_id: str,
    language: Language,
    channel: Channel,
    evidence: tuple[EvidenceRef, ...],
) -> CaregiverMessage:
    """A process-only reply. Never a clinical one, even if the question was."""
    by = f", by {fact.by:%d %B}" if fact.by else ""
    body = _TEMPLATES.get(language, _TEMPLATES[Language.ENGLISH]).format(
        awaiting=fact.awaiting, by=by
    )
    if _contains_any(body, CLINICAL_TERMS) or _contains_any(body, PROHIBITED_PHRASES):
        # Unreachable with the fixed templates above, but a process answer is
        # held to the exact same bar as a rendered plan message, no exceptions.
        return CaregiverMessage(
            patient_id=patient_id,
            language=language,
            channel=channel,
            body="",
            evidence=evidence,
            routed_to_care_team=True,
            routing_reason="process answer failed the content guard",
        )
    if not evidence:
        return CaregiverMessage(
            patient_id=patient_id,
            language=language,
            channel=channel,
            body="",
            evidence=evidence,
            routed_to_care_team=True,
            routing_reason="process answer carries no evidence refs",
        )
    return CaregiverMessage(
        patient_id=patient_id,
        language=language,
        channel=channel,
        body=body,
        evidence=evidence,
    )
