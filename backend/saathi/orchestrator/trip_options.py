"""Weighing the ways of getting there for one family.

Pure: options and the family's money in, a recommendation and its reasons out.
No clock, no network, no rates.

How it decides, in the order that matters to a patient on treatment:

1. **What they can afford comes first, but only where it is known.** An option
   whose cost is known and is more than the room left this month is set aside
   unless every option is over. An option with no known cost is never called
   cheap, and never called dear.
2. **Then the effort.** A journey with fewer changes and less walking is kinder
   to someone tired or unwell, so among options that fit, the fewest changes
   win, then the least walking, then the shortest time.
3. **Then the clock.** If a time to arrive by is given, an option that cannot
   make it is dropped.

The reasons are codes; the screen puts them in the family's language.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, tzinfo

from ..domain.itinerary import (
    Fit,
    Guidance,
    RouteOption,
    Tag,
    Weighed,
)

#: Time to get from the door of a hospital to the desk, and for a late bus.
#: A margin, not a rate: it is shown to the family as the leave-by time.
ARRIVAL_MARGIN = timedelta(minutes=45)


def next_visit_start(
    booked: Iterable[datetime],
    scheduled_days: Iterable[date],
    *,
    tz: tzinfo,
    now: datetime,
) -> datetime | None:
    """When the family's next booked visit starts, as the hospital holds it.

    `booked` are the start times of their open appointments in the hospital's
    system and `scheduled_days` the days their care steps are planned for. A
    day counts only if the hospital actually holds a booking on it: a time is
    never made up for a day that has none, because a "leave by" built on a
    guess would be a promise nobody made. Returns None when there is none.
    """
    upcoming = [b for b in booked if b > now]
    for day in sorted({d for d in scheduled_days}):
        starts = [b for b in upcoming if b.astimezone(tz).date() == day]
        if starts:
            return min(starts)
    return None


def _minimum(values: list[int]) -> int | None:
    return min(values) if values else None


def weigh(
    options: list[RouteOption],
    *,
    room_paise: int | None = None,
    arrive_by: datetime | None = None,
    own_trip_paise: int | None = None,
) -> Guidance:
    if not options:
        return Guidance(options=(), room_paise=room_paise)

    usable = [
        o
        for o in options
        if arrive_by is None or o.arrives is None or o.arrives <= arrive_by
    ]
    dropped_for_time = len(usable) < len(options)
    pool = usable or options

    costs = {o.id: o.fare_paise for o in pool}
    known = [c for c in costs.values() if c is not None]
    cheapest = _minimum(known)
    quickest = min(o.minutes for o in pool)
    slowest = max(o.minutes for o in pool)
    fewest = min(o.changes for o in pool)
    least_walk = min(o.walking_minutes for o in pool)

    weighed: list[Weighed] = []
    for o in pool:
        cost = costs[o.id]
        tags: list[Tag] = []
        if cost is not None and cost == cheapest and len(known) > 1:
            tags.append(Tag.CHEAPEST)
        if o.minutes == quickest and len(pool) > 1:
            tags.append(Tag.FASTEST)
        if o.changes == fewest and len(pool) > 1 and any(p.changes != fewest for p in pool):
            tags.append(Tag.FEWEST_CHANGES)
        if o.walking_minutes == least_walk and any(p.walking_minutes != least_walk for p in pool):
            tags.append(Tag.LEAST_WALKING)
        if cost is None or room_paise is None:
            fit = Fit.UNKNOWN
        else:
            fit = Fit.WITHIN if cost <= room_paise else Fit.OVER
        weighed.append(
            Weighed(
                option=o,
                tags=tuple(tags),
                fit=fit,
                extra_over_cheapest_paise=(
                    (cost - cheapest)
                    if cost is not None and cheapest is not None
                    else None
                ),
                minutes_saved=slowest - o.minutes,
                leave_by=(o.departs - ARRIVAL_MARGIN) if o.departs and arrive_by else (
                    (arrive_by - timedelta(minutes=o.minutes) - ARRIVAL_MARGIN)
                    if arrive_by
                    else None
                ),
            )
        )

    affordable = [w for w in weighed if w.fit is not Fit.OVER]
    candidates = affordable or weighed
    best = min(
        candidates,
        key=lambda w: (
            w.option.changes,
            w.option.walking_minutes,
            w.option.minutes,
            w.option.fare_paise or 0,
        ),
    )

    reasons: list[str] = []
    if dropped_for_time:
        reasons.append("some_too_late")
    if not affordable:
        reasons.append("all_over_budget")
    elif len(affordable) < len(weighed):
        reasons.append("some_over_budget")
    if best.fit is Fit.WITHIN:
        reasons.append("fits_budget")
    if room_paise is None and len(known) > 1 and best.option.fare_paise != cheapest:
        # The gentlest way costs more than another, and we do not know what they can manage.
        reasons.append("say_what_you_can_manage")
    if best.fit is Fit.UNKNOWN and best.option.fare_paise is None:
        reasons.append("cost_unknown")
    if Tag.FEWEST_CHANGES in best.tags:
        reasons.append("fewest_changes")
    if Tag.LEAST_WALKING in best.tags:
        reasons.append("least_walking")
    if Tag.CHEAPEST in best.tags:
        reasons.append("cheapest")
    if Tag.FASTEST in best.tags:
        reasons.append("fastest")

    ordered = sorted(weighed, key=lambda w: (w is not best, w.option.changes, w.option.minutes))
    return Guidance(
        options=tuple(ordered),
        recommended_id=best.option.id,
        reasons=tuple(reasons),
        room_paise=room_paise,
    )
