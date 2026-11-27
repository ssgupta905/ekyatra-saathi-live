"""Putting nearby places in an order a family can act on.

Pure: places and the moment the family will be there, in; an ordered list with
the reasons out. No clock, no network, no ratings.

The order, and why:

1. **Open when they will be there.** A shop that is shut on arrival is no help.
   Places whose hours are unknown rank after those known to be open, not before.
2. **Cheaper first, where that is a thing.** Jan Aushadhi stores sell generics at
   government prices, so for medicines they come first when the family has said
   money is tight; otherwise they are simply the first kind offered.
3. **Closer first.** Straight-line distance, said to be rough; the phone's map
   gives the real travel time on tap.

Nothing here says a place has what the family needs. It cannot know.
"""

from __future__ import annotations

from datetime import datetime
from math import asin, cos, radians, sin, sqrt

from ..domain.places import Place, PlaceKind, Ranked


def metres_between(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Great-circle distance, whole metres."""
    p1, p2 = radians(lat1), radians(lat2)
    a = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2
    return round(2 * 6_371_000 * asin(sqrt(a)))


def rank(
    places: list[Place],
    *,
    near: tuple[float, float],
    at: datetime | None = None,
    money_is_tight: bool = False,
    limit: int = 8,
) -> list[Ranked]:
    ranked: list[Ranked] = []
    seen: set[str] = set()
    for place in places:
        if place.id in seen:
            continue
        seen.add(place.id)
        open_then = place.open_at(at) if at is not None else place.open_now
        reasons: list[str] = []
        if place.is_24h:
            reasons.append("open_round_the_clock")
        elif open_then is True:
            reasons.append("open_then")
        elif open_then is False:
            reasons.append("shut_then")
        else:
            reasons.append("hours_unknown")
        if place.kind is PlaceKind.JAN_AUSHADHI:
            reasons.append("government_price_generics")
        if place.kind is PlaceKind.DHARAMSHALA:
            reasons.append("free_or_nearly_free")
        ranked.append(
            Ranked(
                place=place,
                metres=metres_between(near[0], near[1], place.latitude, place.longitude),
                open_then=open_then,
                reasons=tuple(reasons),
            )
        )

    #: The kinds that cost a family least, promoted when they have said money
    #: is tight. A dharamshala is to a hotel what a Jan Aushadhi store is to a
    #: pharmacy — the same argument, about a bed instead of a box of pills.
    cheapest = {PlaceKind.JAN_AUSHADHI, PlaceKind.DHARAMSHALA}

    def order(r: Ranked):
        shut = 0 if r.open_then is True else 1 if r.open_then is None else 2
        cheap = 0 if (money_is_tight and r.place.kind in cheapest) else 1
        return (shut, cheap, r.metres)

    return sorted(ranked, key=order)[:limit]
