"""A way of getting to the hospital, as steps a person can follow.

"Take the bus" is not a plan. A plan says which bus, boarded where, when it
leaves, where to get off, how far to walk after, and what that costs — and then
says which of the ways on offer suits this family, and why.

The same rule as the rest of the books holds here: **a fare is shown only if
someone gave it.** A route service's own fare, a seller's firm quote, or what
this family's own last trips cost, each carrying its `basis`. When none of those
exists the cost is `None` and the screen says "cost not known", never a typical
rate.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from .models import Base


class StepMode(StrEnum):
    WALK = "walk"
    BUS = "bus"
    METRO = "metro"
    TRAIN = "train"
    TRAM = "tram"
    FERRY = "ferry"
    TAXI = "taxi"
    OTHER = "other"

    @property
    def is_public(self) -> bool:
        return self in {StepMode.BUS, StepMode.METRO, StepMode.TRAIN, StepMode.TRAM, StepMode.FERRY}


class FareBasis(StrEnum):
    #: The route service's own fare for this journey.
    SERVICE = "service"
    #: A seller's firm price for this ride.
    QUOTE = "quote"
    #: What this family's own last trips cost, repeated.
    YOUR_TRIPS = "your_trips"
    NONE = "none"


class Step(Base):
    mode: StepMode
    #: The line as it is painted on the vehicle: "5A", "Western Line", "12951".
    line: str | None = None
    #: Where it is going, as the vehicle shows it.
    towards: str | None = None
    #: Where to get on. Absent for walking and taxis.
    board_at: str | None = None
    get_off_at: str | None = None
    #: Stops to ride, so a person knows when to get off.
    stops: int | None = None
    departs: datetime | None = None
    arrives: datetime | None = None
    minutes: int = Field(ge=0)
    metres: int | None = Field(default=None, ge=0)
    #: Walking and waiting instructions in the route service's own words.
    note: str | None = None


class RouteOption(Base):
    id: str
    steps: tuple[Step, ...]
    minutes: int = Field(ge=0)
    departs: datetime | None = None
    arrives: datetime | None = None
    #: A fare, in whole paise, only when someone gave it.
    fare_paise: int | None = Field(default=None, ge=1)
    fare_basis: FareBasis = FareBasis.NONE
    #: Where the option came from, so a demo is never mistaken for a timetable.
    source: str = "service"

    @property
    def changes(self) -> int:
        """How many times the traveller changes vehicle."""
        return max(sum(1 for s in self.steps if s.mode is not StepMode.WALK) - 1, 0)

    @property
    def walking_minutes(self) -> int:
        return sum(s.minutes for s in self.steps if s.mode is StepMode.WALK)

    @property
    def is_public(self) -> bool:
        return any(s.mode.is_public for s in self.steps)


class Tag(StrEnum):
    CHEAPEST = "cheapest"
    FASTEST = "fastest"
    FEWEST_CHANGES = "fewest_changes"
    LEAST_WALKING = "least_walking"


class Fit(StrEnum):
    """How an option sits against what the family said they can manage."""

    WITHIN = "within"
    OVER = "over"
    #: No limit stated, or no cost known: we do not guess.
    UNKNOWN = "unknown"


class Weighed(Base):
    option: RouteOption
    tags: tuple[Tag, ...] = ()
    fit: Fit = Fit.UNKNOWN
    #: Costs the family this much more than the cheapest known option.
    extra_over_cheapest_paise: int | None = None
    #: Minutes saved against the slowest option.
    minutes_saved: int = 0
    #: Leave by this time to arrive when needed. None when no arrival time is needed.
    leave_by: datetime | None = None


class Guidance(Base):
    options: tuple[Weighed, ...]
    #: The one to suggest. None when there is nothing to choose from.
    recommended_id: str | None = None
    #: Why, as codes the screen puts in the family's language.
    reasons: tuple[str, ...] = ()
    #: What the family said they can manage this month that is still free. None when not said.
    room_paise: int | None = None


__all__ = [
    "FareBasis",
    "Fit",
    "Guidance",
    "RouteOption",
    "Step",
    "StepMode",
    "Tag",
    "Weighed",
]
