"""What a family spends on getting to care, and what the coming month will cost.

The planner never reads anything here. Money may reorder which cab is asked
(`affordability.py`), but what a family has spent must never move a clinical
date, so this module sits beside the plan rather than inside it — and a test
holds that line (`tests/test_kharcha_privacy.py`).

**Every amount has an owner.** This project does not report a fare it was not
given, and a budget is the place that rule is most tempted. So an entry exists
only with a `source` that says who gave the number — the family in their own
words, a provider's quote, a payment the provider says was made, a hospital
bill — and a projection is only ever arithmetic over such entries, carrying the
ids it was worked from. When there is nothing to work from, the answer is "we
cannot say yet", never a typical rate.

**The family is the only person who confirms.** A spend the family typed or
said is `proposed` until they tap that it is right; nobody at the hospital does
it for them, and nobody at the hospital can read it (`api/kharcha.py`).

Amounts are whole paise. A float has no business holding money.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import Field, model_validator

from .models import Base

#: The most a single spend may plausibly be. A family's own figure above this is
#: almost certainly a misheard or mistyped number (an extra zero, a phone number),
#: and recording it would make every projection after it wrong.
MOST_ONE_SPEND_PAISE = 1_00_000 * 100


class SpendCategory(StrEnum):
    """What the money went on, in the words a family would sort it by."""

    TRAVEL = "travel"
    STAY = "stay"
    FOOD = "food"
    #: Pharmacy items. The family's own entry, never what a medicine is.
    MEDICINE = "medicine"
    HOSPITAL = "hospital"
    OTHER = "other"


class SpendStatus(StrEnum):
    #: Read from the family's words; not counted until they say it is right.
    PROPOSED = "proposed"
    #: A provider has named its price for something not yet paid.
    QUOTED = "quoted"
    PAID = "paid"
    REFUNDED = "refunded"
    #: The family said it was wrong, or the provider withdrew it.
    VOID = "void"


class SpendSource(StrEnum):
    """Who gave the number. The reason an amount may be shown at all."""

    FAMILY_STATED = "family_stated"
    PROVIDER_QUOTE = "provider_quote"
    #: A provider's own range before booking (an estimate screen). Never "spent".
    PROVIDER_ESTIMATE = "provider_estimate"
    PAYMENT_WEBHOOK = "payment_webhook"
    HOSPITAL_BILL = "hospital_bill"


class CoveredBy(StrEnum):
    """Who bears the cost. Only ever what was recorded, never assumed from a card."""

    SELF = "self"
    SCHEME = "scheme"
    INSURANCE = "insurance"
    UNKNOWN = "unknown"


class SpendEntry(Base):
    id: str = Field(min_length=1, max_length=96)
    patient_id: str
    category: SpendCategory
    amount_paise: int = Field(ge=1, le=MOST_ONE_SPEND_PAISE)
    #: Only for a provider's estimate, which is a range.
    amount_high_paise: int | None = Field(default=None, ge=1, le=MOST_ONE_SPEND_PAISE)
    status: SpendStatus
    source: SpendSource
    #: The provider's own reference: a payment event, an order, a quote. Required
    #: for anything that did not come from the family, so it can be traced back.
    source_ref: str | None = Field(default=None, max_length=128)
    #: The family's own words, for anything they stated.
    stated_in: str | None = Field(default=None, max_length=400)
    covered_by: CoveredBy = CoveredBy.SELF
    #: When the money was spent, or is due.
    on: date
    #: The visit this belongs to, so a trip's cost can be compared with the next.
    visit_on: date | None = None
    organisation_id: str | None = Field(default=None, max_length=64)
    #: Who was paid, in their own name: "Ola", "Day-care pharmacy".
    party: str | None = Field(default=None, max_length=160)
    #: The vendor's own pay link for this amount, once the family asked to pay.
    #: The money goes to the vendor's account; Saathi only hears that it did.
    pay_account: str | None = Field(default=None, max_length=64)
    pay_link_id: str | None = Field(default=None, max_length=128)
    pay_url: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _has_an_owner(self) -> SpendEntry:
        if self.source is SpendSource.FAMILY_STATED and not (self.stated_in or "").strip():
            raise ValueError("a family's figure is kept with the words it came in")
        if self.source is not SpendSource.FAMILY_STATED and not self.source_ref:
            raise ValueError("a provider's figure is kept with the provider's own reference")
        if self.amount_high_paise is not None:
            if self.source is not SpendSource.PROVIDER_ESTIMATE:
                raise ValueError("only an estimate is a range")
            if self.amount_high_paise < self.amount_paise:
                raise ValueError("a range runs low to high")
        if self.source is SpendSource.PROVIDER_ESTIMATE and self.status is not SpendStatus.QUOTED:
            raise ValueError("an estimate is never spent")
        return self

    @property
    def counts(self) -> bool:
        """Whether this is money the family has actually parted with."""
        return self.status is SpendStatus.PAID and self.source is not SpendSource.PROVIDER_ESTIMATE

    @property
    def out_of_pocket(self) -> bool:
        return self.covered_by in (CoveredBy.SELF, CoveredBy.UNKNOWN)


class StatedLimit(Base):
    """What the family said they can manage in a month. Their figure, in their words.

    Not a judgement of their means — that is derived at read time and never
    stored (`affordability.Means`). This is a number they chose to tell us.
    """

    patient_id: str
    monthly_paise: int = Field(ge=1, le=MOST_ONE_SPEND_PAISE)
    stated_in: str = Field(min_length=1, max_length=400)
    set_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Basis(StrEnum):
    """How a projected figure was arrived at. Shown to the family beside it."""

    #: A provider named this price for this visit.
    QUOTED = "quoted"
    #: What the family's own last visits cost, repeated for each one ahead.
    REPEAT_OF_VISITS = "repeat_of_visits"
    #: Nothing recorded to go on. No figure is given.
    NOTHING_TO_GO_ON = "nothing_to_go_on"


class ProjectionLine(Base):
    category: SpendCategory
    #: None when there is nothing to go on.
    amount_paise: int | None
    basis: Basis
    #: How many past visits the repeat was worked from.
    visits_used: int = 0
    #: The entries the figure was worked from, so "why this number" can show them.
    based_on: tuple[str, ...] = ()


class MonthOutlook(Base):
    """One month: what is spent, what is booked, what is still expected."""

    month: date
    spent_paise: int
    booked_paise: int
    #: None when there are visits ahead and nothing to say what they will cost.
    expected_paise: int | None
    visits_ahead: tuple[date, ...] = ()
    lines: tuple[ProjectionLine, ...] = ()
    #: Spent by category, for the list on the family's screen.
    by_category: dict[str, int] = Field(default_factory=dict)

    @property
    def total_known_paise(self) -> int:
        return self.spent_paise + self.booked_paise + (self.expected_paise or 0)


class NudgeKind(StrEnum):
    """A suggestion the family may act on. Words are the screen's, in their language."""

    #: Nights are costing more than getting there, and a cheaper stay serves the hospital.
    STAY_COSTS_MORE = "stay_costs_more"
    #: Spending on hospital or pharmacy with no scheme card on file.
    SCHEME_MAY_COVER = "scheme_may_cover"
    #: Train fares recorded on a cancer journey: the railways' concession may apply.
    RAIL_CONCESSION = "rail_concession"
    #: This month looks like more than the family said they can manage.
    OVER_WHAT_YOU_SAID = "over_what_you_said"


class Nudge(Base):
    kind: NudgeKind
    #: A real organisation named by the nudge, when it names one.
    organisation_id: str | None = None
    organisation_name: str | None = None


__all__ = [
    "MOST_ONE_SPEND_PAISE",
    "Basis",
    "CoveredBy",
    "MonthOutlook",
    "Nudge",
    "NudgeKind",
    "ProjectionLine",
    "SpendCategory",
    "SpendEntry",
    "SpendSource",
    "SpendStatus",
    "StatedLimit",
]
