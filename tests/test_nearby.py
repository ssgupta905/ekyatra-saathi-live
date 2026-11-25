"""Ordering nearby places, and reading a map service's answer."""

from __future__ import annotations

from datetime import UTC, datetime, time

from saathi.adapters.places.google import parse
from saathi.domain.places import Period, Place, PlaceKind
from saathi.orchestrator.nearby_needs import metres_between, rank

CENTRE = (19.0, 72.84)


def shop(id, kind=PlaceKind.PHARMACY, dlat=0.0, hours=None):
    return Place(
        id=id, name=id, kind=kind, latitude=CENTRE[0] + dlat, longitude=CENTRE[1],
        periods=hours or (), 
    )  # fmt: skip


def daytime():
    return tuple(Period(open_day=d, open_at=time(9), close_day=d, close_at=time(21)) for d in range(7))


# 2026-12-01 is a Tuesday. 06:00 UTC is 11:30 IST; 20:00 UTC is 01:30 IST the next day.
NOON = datetime(2026, 12, 1, 6, 0, tzinfo=UTC)
NIGHT = datetime(2026, 12, 1, 20, 0, tzinfo=UTC)


def test_a_shop_that_is_shut_when_they_arrive_is_said_to_be_shut():
    shut = shop("shut-but-close", dlat=0.0001, hours=daytime())
    open_far = shop("open-far", dlat=0.01, hours=daytime())

    late = rank([shut, open_far], near=CENTRE, at=NIGHT)
    assert all(r.open_then is False and "shut_then" in r.reasons for r in late)

    got = rank([shut, open_far], near=CENTRE, at=NOON)
    assert [r.place.id for r in got] == ["shut-but-close", "open-far"], "both open: the nearer first"


def test_a_round_the_clock_shop_is_open_at_night():
    always = shop("24h", hours=(Period(open_day=0, open_at=time(0)),))
    day_only = shop("day", dlat=-0.0001, hours=daytime())

    got = rank([day_only, always], near=CENTRE, at=NIGHT)

    assert got[0].place.id == "24h" and "open_round_the_clock" in got[0].reasons


def test_unknown_hours_rank_after_known_open_and_say_so():
    got = rank([shop("unknown", dlat=0.0001), shop("open", dlat=0.01, hours=daytime())], near=CENTRE, at=NOON)

    assert [r.place.id for r in got] == ["open", "unknown"]
    assert "hours_unknown" in got[1].reasons


def test_jan_aushadhi_comes_first_when_the_family_has_a_limit():
    jan = shop("jan", PlaceKind.JAN_AUSHADHI, dlat=0.01, hours=daytime())
    near = shop("near", dlat=0.0001, hours=daytime())

    assert rank([near, jan], near=CENTRE, at=NOON, money_is_tight=True)[0].place.id == "jan"
    assert rank([near, jan], near=CENTRE, at=NOON, money_is_tight=False)[0].place.id == "near"


def test_the_distance_is_about_right():
    assert 1000 < metres_between(19.0, 72.84, 19.01, 72.84) < 1200


GOOGLE = {
    "places": [
        {
            "id": "ChIJabc",
            "displayName": {"text": "Sai Medical"},
            "formattedAddress": "Parel, Mumbai",
            "location": {"latitude": 19.0, "longitude": 72.84},
            "nationalPhoneNumber": "022 1234 5678",
            "googleMapsUri": "https://maps.google.com/?cid=1",
            "businessStatus": "OPERATIONAL",
            "currentOpeningHours": {"openNow": True},
            "regularOpeningHours": {
                "periods": [{"open": {"day": 2, "hour": 9, "minute": 0}, "close": {"day": 2, "hour": 21, "minute": 30}}]
            },
        },
        {"id": "gone", "displayName": {"text": "Closed Forever"}, "location": {"latitude": 19, "longitude": 72.8},
         "businessStatus": "CLOSED_PERMANENTLY"},
    ]
}  # fmt: skip


def test_a_places_answer_becomes_places_and_drops_closed_businesses():
    [only] = parse(GOOGLE, PlaceKind.PHARMACY)

    assert only.name == "Sai Medical" and only.phone == "022 1234 5678"
    assert only.open_now is True and only.open_at(NOON) is True and only.open_at(NIGHT) is False


def test_no_rating_is_ever_read():
    from saathi.adapters.places import google

    assert "rating" not in google._FIELDS.lower() and "review" not in google._FIELDS.lower()


# ---- OpenStreetMap


def test_common_opening_hours_are_understood_and_strange_ones_are_not_guessed():
    from saathi.adapters.places.osm import parse_opening_hours

    assert parse_opening_hours("24/7")[0].close_at is None
    week = parse_opening_hours("Mo-Sa 09:00-21:00; Su off")
    assert {p.open_day for p in week} == {1, 2, 3, 4, 5, 6}, "Sunday is off"
    split = parse_opening_hours("Mo-Su 09:00-13:00,16:00-21:00")
    assert len(split) == 14
    assert parse_opening_hours("Mo-Su sunrise-sunset") == ()
    assert parse_opening_hours("PH off") == ()
    assert parse_opening_hours(None) == ()


def test_a_shop_open_past_midnight_is_open_after_midnight():
    from saathi.adapters.places.osm import parse_opening_hours

    p = Place(id="x", name="x", kind=PlaceKind.PHARMACY, latitude=1, longitude=1,
              periods=parse_opening_hours("Mo-Su 20:00-02:00"))  # fmt: skip
    # NIGHT is 01:30 IST on Wednesday, inside Tuesday's 20:00-02:00.
    assert p.open_at(NIGHT) is True and p.open_at(NOON) is False


OVERPASS = {
    "elements": [
        {"type": "node", "id": 1, "lat": 19.0, "lon": 72.84,
         "tags": {"name": "Sai Medical", "amenity": "pharmacy", "opening_hours": "Mo-Sa 09:00-21:00",
                  "phone": "+91 22 1234 5678", "addr:street": "Dr Ambedkar Rd", "addr:suburb": "Parel"}},
        {"type": "way", "id": 2, "center": {"lat": 19.01, "lon": 72.85}, "tags": {"name": "Jan Aushadhi Kendra"}},
        {"type": "node", "id": 3, "lat": 19.0, "lon": 72.8, "tags": {"amenity": "pharmacy"}},
    ]
}  # fmt: skip


def test_an_overpass_answer_becomes_places_and_skips_nameless_ones():
    from saathi.adapters.places.osm import parse as parse_osm

    got = parse_osm(OVERPASS, PlaceKind.PHARMACY)

    assert [p.name for p in got] == ["Sai Medical", "Jan Aushadhi Kendra"]
    assert got[0].phone == "+91 22 1234 5678" and got[0].address == "Dr Ambedkar Rd, Parel"
    assert got[0].open_at(NOON) is True and got[1].open_at(NOON) is None
    assert got[1].latitude == 19.01, "a way's centre is used"
    assert all(p.source == "osm" for p in got)


def test_only_a_point_and_a_category_go_to_the_service():
    from saathi.adapters.places.osm import _query

    q = _query(PlaceKind.PHARMACY, 19.0, 72.84, 3000)

    assert "around:3000,19.0,72.84" in q and "pharmacy" in q


def test_a_mobile_number_is_taken_when_there_is_no_landline():
    from saathi.adapters.places.osm import parse as parse_osm

    got = parse_osm({"elements": [{"type": "node", "id": 9, "lat": 1.0, "lon": 1.0,
                                   "tags": {"name": "X", "mobile": "09892449174",
                                            "opening_hours": "Mo 08:00-23:30; Tu-Su 08:00-23:00"}}]}, PlaceKind.PHARMACY)  # fmt: skip

    assert got[0].phone == "09892449174" and len(got[0].periods) == 7
