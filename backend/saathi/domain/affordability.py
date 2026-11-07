"""What a journey costs a family, and what this family can carry.

Two different facts, deliberately kept apart.

`CostTier` is a property of an **organisation**. A patient dharamshala and a
chain hotel both provide a bed, and the difference between them is not a
clinical one. The tier is declared by whoever maintains the directory, because
this system refuses to invent prices: `tools/geo.py` will not report a fare
unless a service provides one, and a tier we guessed would be the same mistake
wearing a different hat. A tier is an *ordering*, never an amount.

`Means` is a property of a **family**, derived at read time from what they told
onboarding. It is never stored. There is no column anywhere that holds it, for
the same reason there is no column that holds a readiness score (invariant 7):
a number on a family's record invites being sorted by, and this particular
number would sort people by how poor they are.

What the pair is for. A household on a daily wage and a household on a salary
get the same care and different *logistics*. The railway desk before the app
cab. The dharamshala before the hotel. And when a plan can be arranged either
as more nights away or as more journeys, the nights are the ruinous half for
anyone who loses a day's earnings with each one — so that trade flips.

Three things this is careful not to do:

* It never changes a clinical decision. Cost reorders only the needs a family
  pays for out of pocket — see `MEANS_SENSITIVE`. A slot, a doctor and a bed
  are the hospital's to allocate, and ordering those by price would be a
  clinical decision wearing a logistics hat.
* It never *filters*. Every tier stays reachable. A dharamshala with no beds
  must still fall through to a lodge, so this sets the order of asking and the
  existing fall-back chain does the rest.
* It never reaches for the subsidised option on behalf of a family who did not
  say they needed it. A charity bed taken by someone who could have paid for a
  lodge is a bed a destitute family did not get, so `SUBSIDISED` is ranked
  *last* for everyone except a family whose own papers say otherwise.
"""

from __future__ import annotations

from enum import StrEnum


class CostTier(StrEnum):
    """What an organisation costs the family, as an order rather than an amount."""

    #: Free or heavily subsidised, and usually rationed: a patient dharamshala,
    #: a Jan Aushadhi counter, a railway patient quota.
    SUBSIDISED = "subsidised"
    #: Ordinary public provision a family pays for: a state bus, a sleeper
    #: berth, a lodge by the station.
    MODEST = "modest"
    #: Market rate: an app cab, a chain hotel, a private ambulance.
    STANDARD = "standard"


class Means(StrEnum):
    """What a family can carry, in the only terms we have any evidence for."""

    #: Every avoidable rupee matters, and a night away costs a day's earnings.
    STRETCHED = "stretched"
    #: Can meet an ordinary fare and an ordinary room without it being ruinous.
    MODEST = "modest"
    COMFORTABLE = "comfortable"
    #: Nobody has asked yet, or the family chose not to say.
    NOT_STATED = "not_stated"


#: The needs a family pays for out of pocket, and therefore the only ones where
#: cost is allowed any say in who gets asked.
MEANS_SENSITIVE: frozenset[str] = frozenset({"transport", "stay", "medicine"})


#: Ration cards, in the schemes' own words. AAY is the poorest households by
#: the scheme's own definition and BPL is below the poverty line; both are a
#: determination somebody already made with evidence, which is why the card
#: leads and the self-reported income band only fills a gap.
_CARD: dict[str, Means] = {
    "aay": Means.STRETCHED,
    "bpl": Means.STRETCHED,
    "apl": Means.MODEST,
}

#: Income bands, matched loosely on purpose. The field is free text a navigator
#: typed at a counter, so an unrecognised value yields `NOT_STATED` rather than
#: an exception: a profile that will not load is a worse failure than one field
#: going quiet, and a wrong guess here puts a family in the wrong cab.
_BANDS: tuple[tuple[str, Means], ...] = (
    ("below 1 lakh", Means.STRETCHED),
    ("1 to 2 lakh", Means.MODEST),
    ("2 to 3 lakh", Means.MODEST),
)


def means_from(*, ration_card: str = "", income_band: str = "") -> Means:
    """What this family can carry, from what onboarding was told.

    The card leads. A ration card is a determination made against evidence,
    while an income band is a number a frightened family said out loud at a
    hospital counter — and the direction people err in, when asked their income
    by an institution, is not random.
    """
    card = _CARD.get(ration_card.strip().lower())
    if card is not None:
        return card
    band = income_band.strip().lower()
    for text, means in _BANDS:
        if text in band:
            return means
    return Means.NOT_STATED


#: The order to try cost tiers in, per means.
#:
#: Note where `SUBSIDISED` sits. Only a family whose own papers say they are
#: stretched reaches for it first; for everybody else it is last, so that the
#: rationed thing goes to the people it exists for. `NOT_STATED` is treated as
#: `MODEST` rather than as stretched, because presuming poverty of a family who
#: has not said so is both patronising and takes a bed from someone else.
PREFERENCE: dict[Means, tuple[CostTier, ...]] = {
    Means.STRETCHED: (CostTier.SUBSIDISED, CostTier.MODEST, CostTier.STANDARD),
    Means.MODEST: (CostTier.MODEST, CostTier.STANDARD, CostTier.SUBSIDISED),
    Means.COMFORTABLE: (CostTier.STANDARD, CostTier.MODEST, CostTier.SUBSIDISED),
    Means.NOT_STATED: (CostTier.MODEST, CostTier.STANDARD, CostTier.SUBSIDISED),
}


def rank_of(tier: CostTier, means: Means) -> int:
    """Where a tier sits for this family. Lower is asked first."""
    return PREFERENCE[means].index(tier)


def nights_hurt_more_than_trips(means: Means) -> bool:
    """Which half of the nights-versus-trips trade costs this family more.

    A night away is a bed, food, and a day not earning, and for a household on
    a daily wage the third of those bites hardest — every night, again. A
    second journey is a fare: painful once. So a stretched family is offered
    going home and coming back, and everyone else is offered staying put, which
    is the order the planner has always used.
    """
    return means is Means.STRETCHED


def why(tier: CostTier, means: Means) -> str:
    """One plain sentence a navigator and a family can both read.

    Nothing here is allowed to happen silently. If a family was sent to a rail
    desk rather than a cab, the reason is written down and shown.
    """
    if means is Means.NOT_STATED:
        return "nobody has asked this family what they can manage yet"
    if tier is CostTier.SUBSIDISED:
        return "the family's own papers say they are on the lowest band"
    if tier is CostTier.MODEST:
        return "an ordinary fare rather than a market-rate one"
    return "the family has not said cost is a constraint"


__all__ = [
    "MEANS_SENSITIVE",
    "PREFERENCE",
    "CostTier",
    "Means",
    "means_from",
    "nights_hurt_more_than_trips",
    "rank_of",
    "why",
]
