"""The rules that keep an estimate from becoming a lie.

`domain/budget.py` refuses to report a fare it was not given. `money/` is the
narrow exception, and these are the conditions that make it one: a published
basis on every figure, a range rather than false precision, no number ever
attached to a booking company, and the family's own figure beating ours.
"""

from __future__ import annotations

from datetime import date

import pytest
from saathi.domain.places import PlaceKind
from saathi.money import load_rates
from saathi.money.rates import Estimate, JourneyCost


@pytest.fixture(scope="module")
def table():
    return load_rates()


def test_every_rate_names_where_it_came_from(table):
    """A figure a judge cannot trace is a figure we invented."""
    for section in (table.travel, table.stay):
        for key, rate in section.items():
            assert rate.source.strip(), f"{key} has no source"
            assert len(rate.source) > 20, f"{key}'s source is too vague to check"
            assert isinstance(rate.as_of, date)


def test_no_rate_is_attributed_to_a_booking_company():
    """We have no access to their pricing; a number beside their name is a lie.

    They are where a family books, which is a different claim entirely.
    """
    table = load_rates()
    brands = ("irctc", "makemytrip", "oyo", "uber", "ola", "redbus", "goibibo")
    for section in (table.travel, table.stay):
        for key, rate in section.items():
            cited = rate.source.lower()
            for brand in brands:
                assert brand not in cited, f"{key} cites {brand} as a price source"


def test_an_app_cab_has_no_published_rate_and_none_is_invented(table):
    """Surge pricing is set at the moment of booking and published nowhere."""
    assert table.travel_cost("uber", 20) is None
    assert table.travel_cost("ola", 20) is None


def test_a_ticket_is_per_person_and_a_meter_is_per_vehicle(table):
    """Two people in one auto pay once; two people on a train pay twice."""
    one_rail = table.travel_cost("rail_sleeper", 1000, people=1)
    two_rail = table.travel_cost("rail_sleeper", 1000, people=2)
    assert two_rail.low_paise == 2 * one_rail.low_paise

    one_auto = table.travel_cost("auto", 8, people=1)
    two_auto = table.travel_cost("auto", 8, people=2)
    assert two_auto.low_paise == one_auto.low_paise


def test_a_cheaper_bed_is_cheaper(table):
    """The ordering families are promised must hold in the numbers too."""
    cheap = table.stay_cost(PlaceKind.DHARAMSHALA)
    middle = table.stay_cost(PlaceKind.GUEST_HOUSE)
    dear = table.stay_cost(PlaceKind.HOTEL)
    assert cheap.high_paise < middle.high_paise < dear.high_paise


def test_an_estimate_is_a_range_and_says_it_is_an_estimate(table):
    """A single number implies a precision we have not got."""
    fare = table.travel_cost("rail_sleeper", 1200, people=2)
    assert fare.is_range
    assert fare.to_json()["is_estimate"] is True
    assert "–" in fare.rupees()


def test_what_the_family_said_is_not_rendered_as_our_estimate():
    """Their number is evidence. Ours is arithmetic. The screen must differ."""
    theirs = Estimate(
        label="Train, sleeper",
        key="stated_travel",
        low_paise=90000,
        high_paise=90000,
        basis="what the family told us",
        source="the family",
        as_of=date(2026, 11, 27),
        stated=True,
        said="Trainer tickets 900 taka hobe",
    )
    body = theirs.to_json()
    assert body["is_estimate"] is False
    assert body["stated"] is True
    assert body["said"]
    assert theirs.rupees() == "₹900"


def test_a_total_is_itemised_so_a_family_can_argue_with_one_part(table):
    """"₹2,400" is not actionable. "₹1,600 train, ₹800 bed" is."""
    trip = JourneyCost(
        items=(
            table.travel_cost("rail_sleeper", 1300, people=2),
            table.stay_cost(PlaceKind.DHARAMSHALA, nights=1),
        )
    )
    assert len(trip.items) == 2
    assert trip.low_paise == sum(i.low_paise for i in trip.items)
    assert trip.to_json()["has_stated"] is False


def test_a_journey_of_no_distance_costs_nothing_rather_than_a_minimum(table):
    """A family already in the city is not charged a fare for not travelling."""
    assert table.travel_cost("rail_sleeper", 0) is None
    assert table.stay_cost(PlaceKind.HOTEL, nights=0) is None


# ------------------------------------------------------------- costing a trip


def test_a_short_metro_hop_is_a_local_train_not_an_auto(table):
    """Thane to Parel is a ten-rupee train, not a thousand-rupee auto.

    The first version costed everything under 30 km as an auto and told a
    family 25 km away that coming in would cost them ₹552–1147. A figure that
    wrong about a journey the city makes for ten rupees discredits every other
    number on the screen.
    """
    from saathi.money import cost_of_journey, mode_for

    assert mode_for(25) == "rail_local"
    assert mode_for(6) == "auto"
    assert mode_for(300) == "bus_state"
    assert mode_for(1340) == "rail_sleeper"

    near = cost_of_journey(table, km=25, people=1, round_trip_hours=4)
    assert near.high_paise < 10_000, f"a 25 km return should be under ₹100, got {near.rupees()}"


def test_a_trip_is_costed_both_ways(table):
    """A one-way figure is the most misleading number we could show somebody
    deciding whether they can afford to come, because they have to get home."""
    from saathi.money import cost_of_journey

    there_and_back = cost_of_journey(table, km=500, people=1, round_trip_hours=20)
    one_way = table.travel_cost("rail_sleeper", 500, people=1)
    assert there_and_back.items[0].low_paise == pytest.approx(2 * one_way.low_paise, rel=0.01)


def test_a_night_is_only_costed_when_the_trip_needs_one(table):
    """A bed charged to a family who can get home the same day is money we
    have told them to find for nothing."""
    from saathi.money import cost_of_journey, nights_for

    assert nights_for(25, 4) == 0
    assert nights_for(1340, 44) == 1

    same_day = cost_of_journey(
        table, km=25, people=1, round_trip_hours=4, stay_kind=PlaceKind.DHARAMSHALA
    )
    assert all("night" not in i.basis for i in same_day.items)


def test_the_family_s_own_figure_replaces_ours_and_keeps_their_words(table):
    """We do not average our estimate with theirs, and we do not correct them."""
    from saathi.money import cost_of_journey

    costed = cost_of_journey(
        table, km=1340, people=2, round_trip_hours=44,
        stated_paise=90_000, stated_in="Trainer tickets 900 taka hobe",
    )
    travel = costed.items[0]
    assert travel.stated is True
    assert travel.low_paise == travel.high_paise == 90_000
    assert "900 taka" in travel.said
    assert costed.to_json()["has_stated"] is True


def test_a_mix_of_their_fare_and_our_estimate_is_not_credited_to_them(table):
    """A family who said "₹900 for the train" said nothing about a bed.

    Quoting a total of their fare plus our room estimate back as "you told us"
    attributes our arithmetic to them. They notice, and they are right to.
    """
    from saathi.money import cost_of_journey

    mixed = cost_of_journey(
        table, km=1340, people=2, round_trip_hours=44,
        stay_kind=PlaceKind.DHARAMSHALA,
        stated_paise=90_000, stated_in="Trainer tickets 900 taka hobe",
    )
    assert mixed.any_stated is True, "their fare is in there"
    assert mixed.all_stated is False, "but the bed is ours, so the total is ours"

    purely_theirs = cost_of_journey(
        table, km=1340, people=2, round_trip_hours=4,
        stated_paise=90_000, stated_in="Trainer tickets 900 taka hobe",
    )
    assert purely_theirs.all_stated is True


def test_every_cost_line_can_be_said_in_the_family_s_language(table):
    """An English label in the middle of a Devanagari card tells a family this
    app was not built for them.

    The app translates from `key`; `label` is only the fallback for a kind
    nobody has a word for yet. A line with no key would be one the app can
    never say in Hindi, so every one must carry one.
    """
    from saathi.money import cost_of_journey

    costed = cost_of_journey(
        table, km=1340, people=2, round_trip_hours=44,
        stay_kind=PlaceKind.DHARAMSHALA,
        stated_paise=90_000, stated_in="900 taka",
    )
    assert costed.items
    for item in costed.items:
        assert item.key, f"{item.label} has no key, so the app cannot translate it"
        assert item.to_json()["key"] == item.key
