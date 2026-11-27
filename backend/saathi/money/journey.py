"""What one family's trip to one appointment is likely to cost them.

Assembles `money/rates.py` figures into a `JourneyCost` for a real patient and
a real date. Three judgements live here and nowhere else, so they can be argued
with in one place:

**Which mode.** Distance decides, because that is how people actually travel in
India: a few kilometres is an auto, a few hundred is a bus, a thousand-plus is
a train. We cost the cheapest realistic mode rather than the fastest, because
the family this system is for takes the cheapest one.

**Whether a night is needed.** Only when the round trip plus the appointment
genuinely cannot be done between dawn and midnight. A night costed into a trip
that does not need one is money we have told a family to find for nothing.

**Whose number wins.** A figure the family stated replaces ours for the travel
leg entirely, and carries the sentence they said it in. We do not average our
estimate with theirs, and we do not correct them.
"""

from __future__ import annotations

from datetime import date

from saathi.domain.places import PlaceKind

from .rates import Estimate, JourneyCost, RateTable

#: Above this, a train. Below it, a bus. Roughly where an overnight journey
#: starts being the only sensible option on Indian routes.
RAIL_FROM_KM = 400.0

#: Below this a family walks to an auto; there is no train worth the walk.
AUTO_UPTO_KM = 10.0

#: Suburban and passenger rail covers this range in every city with a tertiary
#: cancer hospital, and costs a tenth of anything else. Costing a 25 km trip to
#: Parel as an auto gives about a thousand rupees for a journey Mumbai makes
#: for ten, which is the kind of wrong that discredits every other figure.
LOCAL_RAIL_UPTO_KM = 120.0

#: Hours a round trip can take before a night away is unavoidable. A family
#: leaving at dawn and back by midnight does not pay for a bed.
SAME_DAY_HOURS = 16.0


def mode_for(km: float) -> str:
    """The cheapest realistic way to cover this distance."""
    if km <= AUTO_UPTO_KM:
        return "auto"
    if km <= LOCAL_RAIL_UPTO_KM:
        return "rail_local"
    if km < RAIL_FROM_KM:
        return "bus_state"
    return "rail_sleeper"


def nights_for(km: float, round_trip_hours: float | None) -> int:
    """How many nights away this trip needs. Zero is a real answer.

    Falls back to distance when the router gave us no duration, because a
    thousand kilometres is an overnight journey whether or not OSRM answered.
    """
    if round_trip_hours is not None:
        return 1 if round_trip_hours > SAME_DAY_HOURS else 0
    return 1 if km >= RAIL_FROM_KM else 0


def cost_of_journey(
    table: RateTable,
    *,
    km: float,
    people: int = 1,
    round_trip_hours: float | None = None,
    stay_kind: PlaceKind | str | None = None,
    stated_paise: int | None = None,
    stated_in: str = "",
    as_of: date | None = None,
) -> JourneyCost:
    """Itemise this trip: travel both ways, plus a bed if one is needed.

    `stated_paise` is the family's own figure for the travel. When present it
    replaces our arithmetic for that leg — see the module docstring — and a
    stay is still costed separately, because a family quoting a train fare has
    almost never included the night in it.
    """
    items: list[Estimate] = []

    if stated_paise is not None:
        items.append(
            Estimate(
                label="Travel, both ways",
                low_paise=stated_paise,
                high_paise=stated_paise,
                basis="what the family told us it costs them",
                source="the family",
                as_of=as_of or date.today(),
                stated=True,
                said=stated_in,
            )
        )
    else:
        mode = mode_for(km)
        # Both ways. A one-way figure is the single most misleading number we
        # could put in front of somebody deciding whether they can afford to
        # come, because they have to get home again.
        leg = table.travel_cost(mode, km * 2, people=people)
        if leg is not None:
            items.append(leg)

    nights = nights_for(km, round_trip_hours)
    if nights and stay_kind is not None:
        bed = table.stay_cost(stay_kind, nights=nights)
        if bed is not None:
            items.append(bed)

    return JourneyCost(items=tuple(items))
