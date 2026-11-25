"""Weighing the ways of getting there, and reading a route service's answer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from saathi.adapters.routes.google import parse
from saathi.domain.itinerary import FareBasis, Fit, RouteOption, Step, StepMode, Tag
from saathi.orchestrator.trip_options import weigh

T0 = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


def opt(id, minutes, *, changes=0, walk=0, fare=None, arrives=None):
    steps = [Step(mode=StepMode.WALK, minutes=walk)] if walk else []
    steps += [Step(mode=StepMode.BUS, line=f"{id}-{n}", minutes=1) for n in range(changes + 1)]
    return RouteOption(
        id=id, steps=tuple(steps), minutes=minutes, departs=T0,
        arrives=arrives or T0 + timedelta(minutes=minutes), fare_paise=fare,
        fare_basis=FareBasis.SERVICE if fare else FareBasis.NONE,
    )


def test_a_family_with_little_room_is_not_sent_the_dear_way():
    fast_dear = opt("fast", 40, fare=9000)
    slow_cheap = opt("slow", 70, changes=1, fare=2000)

    guide = weigh([fast_dear, slow_cheap], room_paise=3000)

    assert guide.recommended_id == "slow"
    assert "some_over_budget" in guide.reasons
    over = next(w for w in guide.options if w.option.id == "fast")
    assert over.fit is Fit.OVER and Tag.FASTEST in over.tags


def test_when_every_way_is_over_what_they_said_it_says_so_and_still_helps():
    guide = weigh([opt("a", 50, fare=9000), opt("b", 60, fare=8000)], room_paise=1000)

    assert guide.recommended_id == "a"
    assert "all_over_budget" in guide.reasons


def test_an_unknown_cost_is_never_called_cheap_or_dear():
    guide = weigh([opt("a", 50), opt("b", 60, fare=2000)], room_paise=100)

    unknown = next(w for w in guide.options if w.option.id == "a")
    assert unknown.fit is Fit.UNKNOWN and Tag.CHEAPEST not in unknown.tags
    assert guide.recommended_id == "a", "the dear-looking known fare is out; the unknown stays"


def test_with_money_not_in_question_the_gentlest_journey_wins():
    easy = opt("easy", 65, changes=0, walk=3)
    quick = opt("quick", 50, changes=2, walk=15)

    guide = weigh([quick, easy])

    assert guide.recommended_id == "easy"
    assert "fewest_changes" in guide.reasons and "cost_unknown" in guide.reasons


def test_a_way_that_cannot_arrive_in_time_is_dropped_and_the_leave_by_is_given():
    by = T0 + timedelta(minutes=60)
    late = opt("late", 90)
    ok = opt("ok", 40)

    guide = weigh([late, ok], arrive_by=by)

    assert [w.option.id for w in guide.options] == ["ok"]
    assert "some_too_late" in guide.reasons
    assert guide.options[0].leave_by is not None and guide.options[0].leave_by < by


def test_without_a_stated_limit_the_dearer_gentle_way_comes_with_a_question():
    guide = weigh([opt("easy", 60, fare=9400), opt("hard", 60, changes=2, fare=2000)])

    assert guide.recommended_id == "easy"
    assert "say_what_you_can_manage" in guide.reasons


def test_nothing_to_choose_from_recommends_nothing():
    assert weigh([]).recommended_id is None


# ---- reading Google's Routes answer


DIRECTIONS = {
    "routes": [
        {
            "duration": "3000s",
            "travelAdvisory": {"transitFare": {"currencyCode": "INR", "units": "25"}},
            "legs": [
                {
                    "steps": [
                        {"travelMode": "WALK", "staticDuration": "420s", "distanceMeters": 500,
                         "navigationInstruction": {"instructions": "Walk to Station Road"}},
                        {
                            "travelMode": "TRANSIT",
                            "staticDuration": "2400s",
                            "transitDetails": {
                                "transitLine": {"nameShort": "5A", "vehicle": {"type": "BUS"}},
                                "headsign": "Parel",
                                "stopDetails": {
                                    "departureStop": {"name": "Station Road"},
                                    "arrivalStop": {"name": "Hospital Gate"},
                                    "departureTime": "2026-12-01T03:40:00Z",
                                    "arrivalTime": "2026-12-01T04:20:00Z",
                                },
                                "stopCount": 11,
                            },
                        },
                    ],
                }
            ],
        }
    ],
}


def test_a_directions_answer_becomes_board_here_get_off_there():
    [option] = parse(DIRECTIONS)

    bus = next(s for s in option.steps if s.mode is StepMode.BUS)
    assert (bus.line, bus.board_at, bus.get_off_at, bus.stops) == ("5A", "Station Road", "Hospital Gate", 11)
    assert bus.departs is not None
    assert option.fare_paise == 2500 and option.fare_basis is FareBasis.SERVICE
    assert option.steps[0].note == "Walk to Station Road"


def test_no_fare_in_the_answer_means_no_fare_shown():
    body = {"routes": [{k: v for k, v in DIRECTIONS["routes"][0].items() if k != "travelAdvisory"}]}

    [option] = parse(body)

    assert option.fare_paise is None and option.fare_basis is FareBasis.NONE
