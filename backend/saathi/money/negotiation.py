"""Asking a stay partner for a better rate, on the family's say-so.

A rest house near a cancer centre often gives patient families a better rate
for a longer stay. Nobody asks, because asking is one more thing a tired family
has to do in a city they do not know. Saathi asks for them — but only after
they say "yes, ask", and it books nothing.

The guardrails are the point, and every one of them is on the record:

- **A cap.** Saathi never agrees above what the family can manage: the nightly
  figure they gave us, or the partner's own first price, whichever is lower.
  A negotiation that ends higher than where it started is not a negotiation.
- **At most two rounds.** A partner's desk is a person with a queue; a third
  counter-offer is pestering, and a family waiting on it is waiting for nothing.
- **Only what a room needs.** Dates, how many people, and "hospital visit".
  Never the diagnosis, the hospital, the family's budget or their name. The
  partner learns that a patient family needs a room, which is what a rest
  house's patient rate is for.
- **The family books.** The outcome is a quote, kept with the partner's own
  reference, waiting for the family's tap.

**What the partner's side is, honestly.** In the demo the stay partners are
sandbox stand-ins: `PartnerTerms` is the rate policy a real rest house would
hold, and `partner_reply` is how its booking agent answers. A real partner
plugs its own agent in behind the same two calls. No figure here is attributed
to a named company; a sandbox partner is labelled sandbox wherever it shows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

#: The most rounds Saathi will go before taking the best price it was given.
MAX_ROUNDS = 2


@dataclass(frozen=True)
class PartnerTerms:
    """A stay partner's own rate policy, the thing its booking agent applies.

    `list_nightly_paise` is the price on the door. A patient family staying at
    least `patient_rate_min_nights` may be given up to `best_discount` off it,
    and the partner throws in `includes` at the patient rate.
    """

    list_nightly_paise: int
    best_discount: float = 0.2
    patient_rate_min_nights: int = 2
    includes: tuple[str, ...] = ()

    @property
    def floor_nightly_paise(self) -> int:
        return round_rupee(int(self.list_nightly_paise * (1 - self.best_discount)))


#: Sandbox terms by the directory's cost tier. A rest house beside a hospital,
#: an ordinary lodge and a standard hotel bargain very differently, and the
#: patient discount is largest where the business exists for patients.
SANDBOX_TERMS: dict[str, PartnerTerms] = {
    "subsidised": PartnerTerms(
        list_nightly_paise=400_00,
        best_discount=0.25,
        patient_rate_min_nights=1,
        includes=("one attendant's bed",),
    ),
    "modest": PartnerTerms(
        list_nightly_paise=1_200_00,
        best_discount=0.2,
        patient_rate_min_nights=1,
        includes=("breakfast",),
    ),
    "standard": PartnerTerms(
        list_nightly_paise=2_400_00,
        best_discount=0.15,
        patient_rate_min_nights=2,
        includes=("breakfast",),
    ),
}


def round_rupee(paise: int, to: int = 50) -> int:
    """Prices a desk would actually say: whole rupees, to the nearest fifty."""
    step = to * 100
    return max(step, (paise + step // 2) // step * step)


@dataclass(frozen=True)
class Offer:
    round: int
    by: str  # "saathi" or "partner"
    nightly_paise: int
    note: str = ""

    def to_json(self) -> dict:
        return {
            "round": self.round,
            "by": self.by,
            "nightly_paise": self.nightly_paise,
            "nightly": f"₹{self.nightly_paise // 100:,}",
            "note": self.note,
        }


@dataclass
class Negotiation:
    """What was asked, what came back, and where it ended."""

    partner: str
    nights: int
    party_size: int
    check_in: date
    list_nightly_paise: int
    cap_nightly_paise: int
    offers: list[Offer] = field(default_factory=list)
    agreed_nightly_paise: int | None = None
    includes: tuple[str, ...] = ()

    @property
    def shared(self) -> dict:
        """Everything the partner was told. Nothing else leaves Saathi."""
        return {
            "check_in": self.check_in.isoformat(),
            "nights": self.nights,
            "party_size": self.party_size,
            "purpose": "hospital visit",
        }

    @property
    def rounds(self) -> int:
        return max((o.round for o in self.offers), default=0)

    @property
    def saved_paise(self) -> int:
        if self.agreed_nightly_paise is None:
            return 0
        return (self.list_nightly_paise - self.agreed_nightly_paise) * self.nights

    @property
    def total_paise(self) -> int:
        nightly = self.agreed_nightly_paise or self.list_nightly_paise
        return nightly * self.nights

    def to_json(self) -> dict:
        return {
            "partner": self.partner,
            "nights": self.nights,
            "party_size": self.party_size,
            "list_nightly_paise": self.list_nightly_paise,
            "cap_nightly_paise": self.cap_nightly_paise,
            "agreed_nightly_paise": self.agreed_nightly_paise,
            "total_paise": self.total_paise,
            "saved_paise": self.saved_paise,
            "includes": list(self.includes),
            "rounds": self.rounds,
            "max_rounds": MAX_ROUNDS,
            "offers": [o.to_json() for o in self.offers],
            "shared": self.shared,
        }


def partner_reply(
    terms: PartnerTerms, *, asked_nightly_paise: int, nights: int, round_no: int
) -> Offer:
    """The partner's booking agent answering one counter-offer.

    It accepts anything at or above its floor, refuses a patient rate for a
    stay shorter than its minimum, and otherwise meets the family part of the
    way: halfway on the first round, at its floor on the last.
    """
    if nights < terms.patient_rate_min_nights:
        return Offer(
            round_no,
            "partner",
            terms.list_nightly_paise,
            f"patient rate is for {terms.patient_rate_min_nights}+ nights",
        )
    if asked_nightly_paise >= terms.floor_nightly_paise:
        return Offer(round_no, "partner", asked_nightly_paise, "accepted")
    if round_no >= MAX_ROUNDS:
        return Offer(round_no, "partner", terms.floor_nightly_paise, "best patient rate")
    middle = (terms.list_nightly_paise + asked_nightly_paise) // 2
    return Offer(
        round_no, "partner", round_rupee(max(middle, terms.floor_nightly_paise)), "counter-offer"
    )


def negotiate(
    terms: PartnerTerms,
    *,
    partner: str,
    nights: int,
    party_size: int,
    check_in: date,
    family_nightly_cap_paise: int | None = None,
) -> Negotiation:
    """Two rounds at most, never above the cap, and never above the first price.

    Saathi opens at the partner's likely patient floor or the family's cap,
    whichever is lower — asking for less than a family can pay is how the
    family keeps the difference. If the partner counters, Saathi splits the
    gap once; then it takes the best price it was given, provided that price
    is within the cap. Above the cap it agrees nothing, and says so.
    """
    nights = max(1, nights)
    cap = terms.list_nightly_paise
    if family_nightly_cap_paise:
        cap = min(cap, family_nightly_cap_paise)
    deal = Negotiation(
        partner=partner,
        nights=nights,
        party_size=max(1, party_size),
        check_in=check_in,
        list_nightly_paise=terms.list_nightly_paise,
        cap_nightly_paise=cap,
    )

    ask = round_rupee(min(cap, int(terms.list_nightly_paise * 0.7)))
    for round_no in range(1, MAX_ROUNDS + 1):
        deal.offers.append(Offer(round_no, "saathi", ask, "patient family, " + _stay(nights)))
        reply = partner_reply(terms, asked_nightly_paise=ask, nights=nights, round_no=round_no)
        deal.offers.append(reply)
        if reply.nightly_paise <= ask:
            deal.agreed_nightly_paise = reply.nightly_paise
            break
        if round_no == MAX_ROUNDS or reply.nightly_paise >= terms.list_nightly_paise:
            if reply.nightly_paise <= cap:
                deal.agreed_nightly_paise = reply.nightly_paise
            break
        ask = round_rupee(min(cap, (ask + reply.nightly_paise) // 2))
        if ask >= reply.nightly_paise:
            deal.agreed_nightly_paise = reply.nightly_paise if reply.nightly_paise <= cap else None
            break

    if (
        deal.agreed_nightly_paise is not None
        and deal.agreed_nightly_paise < terms.list_nightly_paise
    ):
        deal.includes = terms.includes
    return deal


def _stay(nights: int) -> str:
    return f"{nights} night" + ("" if nights == 1 else "s")
