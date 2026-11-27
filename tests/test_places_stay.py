"""Somewhere to sleep, and why a dharamshala is its own kind.

A family from Gaya reaches Mumbai after two days. The product could tell them
which train, which station and which pharmacy, and had nothing at all to say
about where they would sleep that night — which is the question anyone
actually travelling asks second, right after how to get there.

The ordering is the point. A dharamshala beside an Indian cancer centre is
free or nearly free, and they exist in numbers precisely because of who
travels to these hospitals. Listed among hotels it is one line in twenty; as
its own kind it comes first, which is the same argument `medicine` already
makes for Jan Aushadhi over an ordinary pharmacy.

No price is attached to any of them, because OSM has none and this project
does not report a fare it was not given.
"""

from __future__ import annotations

from saathi.domain.places import KINDS_FOR_NEED, PlaceKind
from saathi.tools.load_places import kind_of


class TestWhatOpenStreetMapCalls:
    def test_a_hotel_is_a_hotel(self) -> None:
        assert kind_of({"tourism": "hotel", "name": "Hotel Sea Green"}) is PlaceKind.HOTEL

    def test_a_guest_house_and_a_hostel_are_both_guest_houses(self) -> None:
        assert kind_of({"tourism": "guest_house", "name": "Shanti Lodge"}) is PlaceKind.GUEST_HOUSE
        assert kind_of({"tourism": "hostel", "name": "Backpackers"}) is PlaceKind.GUEST_HOUSE

    def test_nothing_of_interest_is_still_nothing(self) -> None:
        assert kind_of({"tourism": "attraction", "name": "Gateway of India"}) is None


class TestFindingADharamshala:
    """OSM has no tag for one, so the name is the only evidence there is."""

    def test_it_is_found_by_name_however_it_is_spelled(self) -> None:
        for name in (
            "Jalaram Dharamshala",
            "Shree Dharmashala Trust",
            "Bhakti Dharamsala",
            "Yatri Niwas",
            "Yatri Nivas Parel",
            "Railway Musafir Khana",
            "Seva Sadan",
        ):
            assert kind_of({"tourism": "guest_house", "name": name}) is PlaceKind.DHARAMSHALA, name

    def test_it_wins_over_the_tag_that_carries_it(self) -> None:
        """Mapped as a guest house or a hostel, and sometimes as a shelter.
        Whatever the tag says, the name is the more useful answer — exactly
        the argument Jan Aushadhi makes against `amenity=pharmacy`."""
        assert (
            kind_of({"tourism": "hotel", "name": "Dharamshala Trust Bhavan"})
            is PlaceKind.DHARAMSHALA
        )

    def test_an_ordinary_hotel_is_not_mistaken_for_one(self) -> None:
        assert kind_of({"tourism": "hotel", "name": "Hotel Saravana"}) is PlaceKind.HOTEL

    def test_a_pharmacy_inside_a_hotel_is_still_a_pharmacy(self) -> None:
        """Stay is checked last for this reason: a family asking for medicine
        must not be sent to a hotel that happens to have a chemist in it."""
        assert (
            kind_of({"tourism": "hotel", "amenity": "pharmacy", "name": "Hotel Blue Chemist"})
            is PlaceKind.PHARMACY
        )


def test_the_cheapest_place_to_sleep_is_offered_first() -> None:
    """The whole reason these are three kinds and not one."""
    assert KINDS_FOR_NEED["stay"] == (
        PlaceKind.DHARAMSHALA,
        PlaceKind.GUEST_HOUSE,
        PlaceKind.HOTEL,
    )


def test_every_stay_kind_belongs_to_the_stay_need() -> None:
    """A kind nobody can ask for is a kind that gets loaded and never shown."""
    asked_for = {k for kinds in KINDS_FOR_NEED.values() for k in kinds}
    for kind in (PlaceKind.DHARAMSHALA, PlaceKind.GUEST_HOUSE, PlaceKind.HOTEL):
        assert kind in asked_for, kind


def test_every_kind_the_google_service_may_be_asked_for_has_a_query() -> None:
    """Adding a PlaceKind must not be able to 500 the screen.

    `nearby` used to index straight into the query table, so three new kinds
    for "somewhere to sleep" turned `/nearby?need=stay` into an Internal
    Server Error. The lookup is defensive now; this is the other half, so the
    defence is never the thing that silently answers "none near here".
    """
    from saathi.adapters.places.google import _QUERY

    unmapped = [k for k in PlaceKind if k not in _QUERY]
    assert unmapped == [], f"no Google query for: {[k.value for k in unmapped]}"
