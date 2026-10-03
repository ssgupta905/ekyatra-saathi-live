"""What a plan costs the family, measured rather than asserted.

`PlanOption.nights_added` and `extra_trips` are the two numbers a navigator
actually weighs, and until now they were passed in by hand at each call site —
which meant the option table could say "+4 nights" whether or not the plan it
described added four nights. This module derives them from the step dates, so a
candidate cannot claim a cost it does not have.

The two quantities are not interchangeable and the trade between them is the
whole decision:

* **Nights** are what a family pays for in a city they do not live in — a bed,
  food, and a day not earning. Waiting three days in Mumbai for a rescheduled
  scan costs three nights.
* **Trips** are the 30-hour train journeys. Going home and coming back saves
  the nights and buys two more journeys.

Neither dominates. A family a long way out will often take the nights; one
close by will take the trip. Saathi measures both and lets a person choose.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from ..domain.enums import TRAVEL_STEPS
from ..domain.models import CareStep

#: Used only when no policy is supplied — see `HospitalPolicy.gap_days`, which
#: is the real answer and reads a *fetched* journey duration rather than a
#: distance. Kept small on purpose: assuming a family will cheerfully wait a
#: week in a strange city is the expensive assumption to get wrong.
FALLBACK_GAP_DAYS = 2


@dataclass(frozen=True)
class Stay:
    """One continuous period away from home."""

    arrive: date
    depart: date

    @property
    def nights(self) -> int:
        return (self.depart - self.arrive).days


@dataclass(frozen=True)
class Itinerary:
    """Every stay a plan implies, and what they add up to."""

    stays: tuple[Stay, ...]

    @property
    def nights(self) -> int:
        return sum(stay.nights for stay in self.stays)

    @property
    def trips(self) -> int:
        """Separate stays away from home."""
        return len(self.stays)

    @property
    def journeys(self) -> int:
        """Legs the family travels. Each stay costs one out and one back.

        This, not `trips`, is what the family feels: Shambhu's "go home and
        come back" option is one extra stay but *two* more 30-hour train
        journeys, and 60 hours on a train is the number worth showing.
        """
        return len(self.stays) * 2

    def __sub__(self, baseline: Itinerary) -> tuple[int, int]:
        """`(nights_added, extra_journeys)` against a baseline itinerary."""
        return (self.nights - baseline.nights, self.journeys - baseline.journeys)


def visit_dates(
    steps: Iterable[CareStep],
    *,
    not_before: date | None = None,
) -> tuple[date, ...]:
    """The distinct days this plan requires the family to be at a hospital.

    Report steps are excluded by construction — `TRAVEL_STEPS` is the set of
    things somebody has to physically attend, and nobody travels to collect a
    result. Two steps on one day are one visit, which is the entire point of
    bundling.
    """
    days = {
        step.scheduled_for
        for step in steps
        if step.kind in TRAVEL_STEPS
        and step.scheduled_for is not None
        and (not_before is None or step.scheduled_for >= not_before)
    }
    return tuple(sorted(days))


def itinerary(
    steps: Sequence[CareStep],
    *,
    not_before: date | None = None,
    gap_days: int = FALLBACK_GAP_DAYS,
) -> Itinerary:
    """Group the plan's visits into stays.

    Consecutive visits closer together than `gap_days` belong to one stay: the
    family waits rather than travelling home. A wider gap splits the stay, and
    costs a journey.
    """
    days = visit_dates(steps, not_before=not_before)
    if not days:
        return Itinerary(stays=())

    # A family already in the city does not start their stay again on the day
    # of their next appointment — they have been paying for a bed since they
    # arrived. Without this the whole stay appears to *slide* when a scan moves,
    # costing nothing, when what actually happens is that it *stretches*: the
    # difference between "+0 nights" and the four nights Shambhu would really
    # have paid for.
    if not_before is not None and any(
        step.kind in TRAVEL_STEPS
        and step.scheduled_for is not None
        and step.scheduled_for < not_before
        for step in steps
    ):
        days = (not_before, *days)

    stays: list[Stay] = []
    start = previous = days[0]
    for day in days[1:]:
        if (day - previous).days > gap_days:
            stays.append(Stay(arrive=start, depart=previous))
            start = day
        previous = day
    stays.append(Stay(arrive=start, depart=previous))
    return Itinerary(stays=tuple(stays))


def compare(
    candidate: Sequence[CareStep],
    baseline: Sequence[CareStep],
    *,
    not_before: date | None = None,
    gap_days: int = FALLBACK_GAP_DAYS,
) -> tuple[int, int]:
    """`(nights_added, extra_trips)` of a candidate plan against the current one.

    Both are measured from `not_before` — usually today — because nights the
    family has already spent are not a cost either option can still avoid.
    """
    candidate_trip = itinerary(candidate, not_before=not_before, gap_days=gap_days)
    baseline_trip = itinerary(baseline, not_before=not_before, gap_days=gap_days)
    return candidate_trip - baseline_trip
