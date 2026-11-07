"""Asking a family what they can actually manage, and recording what they said.

The planner can work out that a journey needs a ride and a bed. It cannot work
out whether this household can pay for the ones it picked, and guessing is how
a family ends up with a confirmed app cab they quietly cannot afford and a
visit they therefore do not make. `affordability.py` narrows the choice from
what their papers say; this is the other half — asking them.

Three rules shape what is here.

**Every option is a real organisation.** The choices are built from the
directory, by `orchestrator/budget.py`, filtered to the ones that actually
serve this family's district and hospital. Nothing is composed for the screen.
A family who taps "railway patient quota desk" is choosing a desk that exists
and that will be asked (invariant 4: nothing reaches a family without a
source).

**The answer is a proposal, not an instruction.** Like `PatientRequest`, a
`BudgetAnswer` carries `confirmed_by` and nothing moves until a navigator has
agreed. Mishearing a tapped option matters less than mishearing prose, but the
family's own words come back with it, and a spoken answer is transcribed —
which is exactly the kind of reading that must not be believed on sight.

**"I cannot manage any of these" is always on the list.** It is the most
important answer and the one a priced menu usually has no room for. It is not
a plan change: it routes to the social-work desk, the same place
`RequestIntent.NEEDS_HELP` already goes, because the answer to a family with no
fare is a person and a scheme, not a cheaper cab.

Nothing here holds money. There is no amount, no quote and no total, because
this project does not report a fare it was not given.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .affordability import CostTier
from .enums import ReadinessKind
from .models import Base


class BudgetTopic(StrEnum):
    """The parts of a journey the family pays for, and so may be asked about."""

    TRAVEL = "travel"
    STAY = "stay"
    MEDICINE = "medicine"


#: Which need an answer settles. Only the three the family buys themselves —
#: the same three as `affordability.MEANS_SENSITIVE`, for the same reason.
TOPIC_NEED: dict[BudgetTopic, ReadinessKind] = {
    BudgetTopic.TRAVEL: ReadinessKind.TRANSPORT,
    BudgetTopic.STAY: ReadinessKind.STAY,
    BudgetTopic.MEDICINE: ReadinessKind.MEDICINE,
}

#: Onboarding's `PartnersSection` key each topic writes into, so a confirmed
#: answer becomes the `preferred_id` the partner desk already honours. The
#: conversation needs no plumbing of its own; it fills in a field that has been
#: there all along.
TOPIC_CHOICE_KEY: dict[BudgetTopic, str] = {
    BudgetTopic.TRAVEL: "transport",
    BudgetTopic.STAY: "stay",
    BudgetTopic.MEDICINE: "medicine",
}


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BudgetOption(_Frozen):
    """One real organisation, offered to the family as something they may choose."""

    organisation_id: str = Field(min_length=1, max_length=64)
    #: The organisation's own name. Not a label written for this screen.
    name: str = Field(min_length=1, max_length=160)
    #: What it offers, in its own words from the directory: "sleeper class",
    #: "low-cost beds for patients". Never a price.
    what: tuple[str, ...] = ()
    cost_tier: CostTier
    #: True for the one the system would have asked anyway. Shown as a
    #: suggestion, never pre-selected: a tapped default is not an answer.
    suggested: bool = False


class BudgetAsk(_Frozen):
    """The question put to one family about one topic."""

    patient_id: str
    topic: BudgetTopic
    options: tuple[BudgetOption, ...] = ()
    #: The need this settles, so the console can say which row it unblocks.
    need: ReadinessKind

    @property
    def answerable(self) -> bool:
        """A question with nothing real to offer is not asked at all.

        Showing a family an empty menu teaches them the app wastes their time,
        and they stop reading it — which costs more than the question saved.
        """
        return bool(self.options)


class BudgetAnswer(Base):
    """What the family said. A proposal until a navigator confirms it."""

    patient_id: str
    topic: BudgetTopic
    #: What they chose, or None when they said they cannot manage any of it.
    organisation_id: str | None = None
    #: True when the family said the fare is not there. Routed to the
    #: social-work desk, never to the planner.
    needs_help: bool = False
    #: Their own words, when they spoke rather than tapped. Kept so a navigator
    #: can check the transcription against the option it was matched to.
    said: str = Field(default="", max_length=400)
    answered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    #: Empty until a person agrees this is what the family meant.
    confirmed_by: str = Field(default="", max_length=120)

    @property
    def confirmed(self) -> bool:
        return bool(self.confirmed_by)


__all__ = [
    "TOPIC_CHOICE_KEY",
    "TOPIC_NEED",
    "BudgetAnswer",
    "BudgetAsk",
    "BudgetOption",
    "BudgetTopic",
]
