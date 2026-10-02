"""The holding message: "don't travel yet", sent before any new date exists.

Deliberately **not** a model call. The brief's requirement is that this goes
out within minutes, with a fixed shape — "today's visit is off, don't travel,
a new plan is coming within N hours" — and templating a fixed-shape sentence
is both faster and safer than asking a language model to improvise one while
no plan yet exists for it to be bound to. `check_outbound`'s machinery does
not apply here (there is no `VisitPlan` yet to check against); the evidence
requirement is enforced directly instead, the same rule in a smaller body.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..domain.enums import Channel, Language
from ..domain.models import Disruption, EvidenceRef, HoldingMessage

_TEMPLATES: dict[Language, str] = {
    Language.HINDI: (
        "Aaj ki visit abhi ke liye rukh gayi hai. Kahin mat jaaiye. "
        "Naya samay {hours} ghante mein bataya jaayega."
    ),
    Language.BENGALI: (
        "Ajker dekha এখনই স্থগিত। কোথাও যাবেন না। "
        "{hours} ঘণ্টার মধ্যে নতুন সময় জানানো হবে।"
    ),
    Language.ODIA: (
        "ଆଜିର ପରିଦର୍ଶନ ବର୍ତ୍ତମାନ ପାଇଁ ବନ୍ଦ ଅଛି। କେଉଁଠାକୁ ଯାଆନ୍ତୁ ନାହିଁ। "
        "{hours} ଘଣ୍ଟା ମଧ୍ୟରେ ନୂଆ ସମୟ କୁହାଯିବ।"
    ),
    Language.ENGLISH: (
        "Today's visit is on hold. Please do not travel. "
        "A new time will reach you within {hours} hours."
    ),
}


def render_holding_message(
    disruption: Disruption,
    patient_id: str,
    language: Language,
    channel: Channel,
    evidence: tuple[EvidenceRef, ...],
    *,
    hours: int = 2,
) -> HoldingMessage:
    """A fixed-shape, evidence-bound "wait" message.

    The brief's hard requirement is ordering, not wording: this must be
    constructible and sendable with zero model latency, so it can go out
    before anyone has computed what the new plan will be.
    """
    body = _TEMPLATES.get(language, _TEMPLATES[Language.ENGLISH]).format(hours=hours)
    return HoldingMessage(
        patient_id=patient_id,
        disruption_id=disruption.id,
        language=language,
        channel=channel,
        body=body,
        evidence=evidence,
        sent_at=datetime.now(UTC),
    )
