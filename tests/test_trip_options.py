"""Weighing the ways of getting there, and reading a route service's answer."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta, timezone

import httpx
from saathi.adapters.routes.google import GoogleRoutes, parse
from saathi.domain.itinerary import FareBasis, Fit, RouteOption, Step, StepMode, Tag
from saathi.orchestrator.trip_options import next_visit_start, weigh
from saathi.ports.routes import Place

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
    assert (bus.line, bus.board_at, bus.get_off_at, bus.stops) == (
        "5A",
        "Station Road",
        "Hospital Gate",
        11,
    )
    assert bus.departs is not None
    assert option.fare_paise == 2500 and option.fare_basis is FareBasis.SERVICE
    assert option.steps[0].note == "Walk to Station Road"


def test_no_fare_in_the_answer_means_no_fare_shown():
    body = {"routes": [{k: v for k, v in DIRECTIONS["routes"][0].items() if k != "travelAdvisory"}]}

    [option] = parse(body)

    assert option.fare_paise is None and option.fare_basis is FareBasis.NONE


# ---- one drive is one step, and ids never repeat between modes


def _drive_body():
    turns = [
        {"travelMode": "DRIVE", "staticDuration": "600s", "distanceMeters": 9000},
        {"travelMode": "DRIVE", "staticDuration": "1200s", "distanceMeters": 40000},
        {"travelMode": "DRIVE", "staticDuration": "300s", "distanceMeters": 2000},
    ]
    return {"routes": [{"duration": "2100s", "legs": [{"steps": turns}]}]}


def _ask(mode):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_drive_body())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    routes = GoogleRoutes("test-key", client=client)
    return asyncio.run(routes.options(Place("Gaya"), Place("19.0,72.8"), mode=mode))


def test_a_drive_is_one_step_not_one_per_turn_of_the_road():
    [drive] = _ask("driving")

    assert len(drive.steps) == 1 and drive.steps[0].mode is StepMode.TAXI
    assert drive.steps[0].metres == 51000
    assert drive.changes == 0


def test_a_long_drive_is_not_ranked_as_a_hundred_changes_of_vehicle():
    """Before, 117 road steps counted as 116 changes and sank it below any bus."""
    [drive] = _ask("driving")
    bus = opt("bus", 2000, changes=1)

    weighed = weigh([bus, drive]).options

    assert drive.changes < bus.changes
    assert len(weighed) == 2


def test_the_transit_and_drive_answers_get_different_ids():
    [drive] = _ask("driving")
    [transit] = parse(_drive_body(), prefix="google-transit")

    assert drive.id != transit.id
    assert drive.id.startswith("google-driving")


# ---- when the next visit starts, from the hospital's own bookings

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 11, 27, 0, 0, tzinfo=UTC)


def test_the_next_visit_is_the_booking_on_the_next_planned_day():
    booked = [datetime(2026, 12, 1, 2, 30, tzinfo=UTC)]  # 08:00 in India

    assert next_visit_start(booked, [date(2026, 12, 1)], tz=IST, now=NOW) == booked[0]


def test_a_planned_day_with_no_booking_is_skipped_not_guessed():
    booked = [datetime(2026, 12, 3, 4, 0, tzinfo=UTC)]

    got = next_visit_start(booked, [date(2026, 12, 1), date(2026, 12, 3)], tz=IST, now=NOW)

    assert got == booked[0]


def test_with_no_booking_there_is_no_time():
    assert next_visit_start([], [date(2026, 12, 1)], tz=IST, now=NOW) is None
    assert next_visit_start([datetime(2026, 12, 1, 2, 30, tzinfo=UTC)], [], tz=IST, now=NOW) is None


def test_a_booking_already_past_does_not_count():
    past = [datetime(2026, 11, 26, 2, 30, tzinfo=UTC)]

    assert next_visit_start(past, [date(2026, 11, 26)], tz=IST, now=NOW) is None


def test_the_day_is_read_in_the_hospitals_timezone():
    """01:30 in India on the 1st is still the 30th in UTC."""
    booked = [datetime(2026, 11, 30, 20, 0, tzinfo=UTC)]

    assert next_visit_start(booked, [date(2026, 12, 1)], tz=IST, now=NOW) == booked[0]
    assert next_visit_start(booked, [date(2026, 12, 1)], tz=UTC, now=NOW) is None
