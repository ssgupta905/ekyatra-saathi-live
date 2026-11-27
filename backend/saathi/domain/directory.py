"""The network a journey runs through: labs, pharmacies, distributors, cabs, hotels.

Reference data an administrator maintains, like the hospital registry. An
organisation says what it does and where, never anything about a family. Which
one a journey uses is chosen by `orchestrator`, from this directory.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .affordability import CostTier

#: The most Saathi may ever take from a vendor's work, in percent.
#:
#: A cap rather than a setting. The reason is the whole economics of this
#: system: a commission that can rise without limit ends up priced into what
#: the vendor charges, and the family pays it without ever seeing a line for
#: it. Capping it in the domain — not in a config file an operator can edit —
#: means the ceiling survives a deployment. `tests/test_vendor_network.py`
#: proves separately that it never reaches a family's bill at all.
MOST_COMMISSION_PCT = 8.0


class VendorRate(BaseModel):
    """One line of a vendor's own price list, in the vendor's own words.

    Stated, never inferred. This system already distinguishes a figure a
    family or a vendor gave it from one it worked out itself — see
    `money/rates.py` — and a rate card is the vendor's side of exactly that
    distinction. Saathi does not negotiate these, discount them, or average
    them into an estimate it then attributes to the vendor.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: What the money buys, as the vendor would write it on a board:
    #: "Gaya to Mumbai, sleeper", "twin room with attached bath", "home delivery".
    service: str = Field(min_length=1, max_length=120)
    #: What it is charged by: per trip, per night, per km, per delivery.
    unit: str = Field(default="per trip", max_length=40)
    amount_inr: int = Field(ge=1, le=10_00_000)
    #: Anything that changes the price and would otherwise surprise somebody:
    #: "₹200 more after 10pm", "two sharing", "excludes toll".
    note: str = Field(default="", max_length=200)


class OrgType(StrEnum):
    HOSPITAL = "hospital"
    LAB = "lab"
    PHARMACY = "pharmacy"
    MEDICINE_DISTRIBUTOR = "medicine_distributor"
    EQUIPMENT_DISTRIBUTOR = "equipment_distributor"
    SHOP = "shop"
    CAB = "cab"
    TRAVEL = "travel"
    HOTEL = "hotel"
    INSURER = "insurer"
    AMBULANCE = "ambulance"


class PartnerMode(StrEnum):
    #: Answers by itself, so a journey moves in a demonstration.
    SIMULATED = "simulated"
    #: Waits for a person at the organisation to answer.
    PEOPLE = "people"
    #: Reached over an open network (Beckn/ONDC): searched, quoted by the
    #: seller itself, and booked only when the family taps Book.
    LIVE = "live"


class Organisation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    type: OrgType
    #: What it offers, in a few plain words: "MRI", "cold chain", "airport pickup".
    services: tuple[str, ...] = ()
    #: What it costs the family, as an order rather than an amount. Declared by
    #: whoever maintains the directory, never inferred: this project will not
    #: report a fare it was not given, and it will not invent a tier either.
    #: The default is `STANDARD` on purpose — an organisation nobody has looked
    #: at should never be mistaken for a cheap one and offered to a family who
    #: cannot afford to be wrong about it.
    cost_tier: CostTier = CostTier.STANDARD
    #: Districts or cities it serves. Empty means it is not tied to a place.
    districts: tuple[str, ...] = ()
    #: The hospitals it works with. Empty means any.
    hospital_ids: tuple[str, ...] = ()
    address: str = Field(default="", max_length=240)
    contact: str = Field(default="", max_length=120)
    hours: str = Field(default="", max_length=80)
    mode: PartnerMode = PartnerMode.SIMULATED
    #: For a simulated organisation: how it answers a request.
    answer: str = Field(default="ready", pattern="^(ready|cannot)$")
    delay_seconds: int = Field(default=30, ge=0, le=3600)
    #: Who to turn to when this one cannot.
    alternate_id: str | None = None
    #: Other organisations it is linked to: a distributor supplies a pharmacy.
    linked_ids: tuple[str, ...] = ()
    #: For a LIVE organisation: which configured network it is reached through.
    provider: str | None = Field(default=None, max_length=64)
    #: The vendor's own payment gateway account, when it takes payment by link.
    #: Money goes from the family to the vendor through it, never through Saathi.
    payment_account: str | None = Field(default=None, max_length=64)
    active: bool = True

    #: What this vendor charges, stated by the vendor itself. Empty for an
    #: organisation an administrator entered from a phone call.
    rate_card: tuple[VendorRate, ...] = ()
    #: What Saathi takes on this vendor's work. Capped by the domain, and never
    #: added to the family's price: a vendor's quote is what the family is told
    #: and what the family pays, and the commission comes out of the vendor's
    #: side of it. Zero by default, because a vendor nobody has agreed terms
    #: with is not paying anything.
    commission_pct: float = Field(default=0.0, ge=0.0, le=MOST_COMMISSION_PCT)

    #: Set when this vendor applied for itself rather than being entered by an
    #: administrator. An application *is* an organisation — with `active` false,
    #: so every routing rule in the system already skips it without being told
    #: to — and approval is the day somebody turned it on.
    applied_on: date | None = None
    approved_on: date | None = None
    #: What the applicant said about itself, in its own words. Read by whoever
    #: reviews it; never shown to a family and never used to route anything.
    applicant_note: str = Field(default="", max_length=600)
    #: Why an application was turned down, so a second reviewer is not left
    #: guessing and the vendor can be told something true.
    declined_reason: str = Field(default="", max_length=300)

    @property
    def awaiting_review(self) -> bool:
        """Applied for itself, and nobody has decided yet."""
        return (
            self.applied_on is not None
            and self.approved_on is None
            and not self.declined_reason
        )

    @property
    def declined(self) -> bool:
        return bool(self.declined_reason)

    def commission_paise(self, quote_paise: int) -> int:
        """Saathi's share of a quote — taken off the vendor, not added to the family.

        Rounded down, so a rounding error is never in Saathi's favour.
        """
        return int(quote_paise * self.commission_pct / 100)


#: Which organisation types answer which kind of need on a journey.
NEED_FOR_TYPE: dict[str, tuple[OrgType, ...]] = {
    "transport": (OrgType.CAB, OrgType.TRAVEL),
    "stay": (OrgType.HOTEL,),
    "medicine": (OrgType.PHARMACY,),
    "insurance": (OrgType.INSURER,),
    #: The hospital's own slot first; a diagnostic centre's when it has none.
    "slot": (OrgType.HOSPITAL, OrgType.LAB),
    "doctor": (OrgType.HOSPITAL,),
    "bed": (OrgType.HOSPITAL,),
}
