"""Building the question: which real organisations to put in front of a family.

Lives here rather than in `domain` because it reads the directory, and the
directory is what this layer is for. The models it fills in are in
`domain/budget.py`.

The shape of the offer is the whole point. A family is shown **one
organisation per cost tier**, cheapest-for-them first, so the choice is
between genuinely different kinds of thing — a patient quota berth, a state
bus, an app cab — rather than three cabs at three prices. Offering five
near-identical options to somebody reading on a 2G phone in a second language
is not more choice; it is a way of not being answered.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..domain.affordability import PREFERENCE, CostTier, Means
from ..domain.budget import TOPIC_NEED, BudgetAsk, BudgetOption, BudgetTopic
from ..domain.directory import NEED_FOR_TYPE, Organisation
from .rules import choose_organisation


def _fits(
    organisations: Sequence[Organisation], types: tuple, district: str, hospital_id: str
) -> list[Organisation]:
    place = district.strip().lower()
    return [
        o
        for o in organisations
        if o.active
        and o.type in types
        and (not o.districts or place in {d.lower() for d in o.districts})
        and (not o.hospital_ids or hospital_id in o.hospital_ids)
    ]


def offer(
    topic: BudgetTopic,
    *,
    patient_id: str,
    district: str,
    hospital_id: str,
    organisations: Sequence[Organisation],
    means: Means = Means.NOT_STATED,
) -> BudgetAsk:
    """What to ask this family about this part of their journey.

    One option per tier, ordered the way `affordability.PREFERENCE` would ask,
    so the first row is the one their own papers point at and the rest are
    there to be chosen instead. The system's own pick is marked `suggested` but
    never pre-selected — a default that was merely not changed is not an answer
    to "what can you manage", and treating it as one is how the question
    becomes decoration.
    """
    need = TOPIC_NEED[topic]
    types = NEED_FOR_TYPE.get(need.value, ())
    fits = _fits(organisations, types, district, hospital_id)

    would_ask = choose_organisation(
        need,
        district=district,
        hospital_id=hospital_id,
        organisations=organisations,
        means=means,
    )

    options: list[BudgetOption] = []
    for tier in PREFERENCE[means]:
        in_tier = [o for o in fits if o.cost_tier is tier]
        if not in_tier:
            continue
        #: Within a tier, the same order the desk itself uses, so the family is
        #: shown the organisation that would actually be asked.
        best = min(in_tier, key=lambda o: (types.index(o.type), o.name.lower()))
        options.append(
            BudgetOption(
                organisation_id=best.id,
                name=best.name,
                what=best.services,
                cost_tier=tier,
                suggested=would_ask is not None and best.id == would_ask.id,
            )
        )

    return BudgetAsk(patient_id=patient_id, topic=topic, options=tuple(options), need=need)


def topics_worth_asking(needs: Sequence) -> tuple[BudgetTopic, ...]:
    """Only ask about the parts of the journey this trip actually involves.

    A family going home the same evening has no stay to pay for, and asking
    them which hotel they can afford is the kind of question that makes people
    stop trusting the screen.
    """
    wanted = {n for n in needs}
    return tuple(t for t in BudgetTopic if TOPIC_NEED[t] in wanted)


__all__ = ["CostTier", "offer", "topics_worth_asking"]
