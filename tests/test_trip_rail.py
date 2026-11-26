"""The long and the last leg of a journey: what the endpoint says, and what it will not claim."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from saathi.api import trip as trip_api
from saathi.domain.itinerary import RouteOption, Step, StepMode
from saathi.domain.railways import HOME_STATIONS, RailHint, arrival_stations, rail_hint
from saathi.main import create_app


class FakeRoutes:
    """A route service that finds only a very long drive, as Google does for an intercity trip."""

    name = "fake"

    def __init__(self, *, transit=False, drive_minutes=1907):
        self.transit = transit
        self.drive_minutes = drive_minutes
        self.asked = []

    async def options(self, origin, destination, *, mode, arrive_by=None, depart_at=None):
        self.asked.append((origin.text, mode))
        if mode == "driving":
            step = Step(mode=StepMode.TAXI, minutes=self.drive_minutes)
            return [
                RouteOption(id="drive-0", steps=(step,), minutes=self.drive_minutes, source="fake")
            ]
        if self.transit:
            bus = Step(mode=StepMode.BUS, line="6", minutes=30)
            return [RouteOption(id="bus-0", steps=(bus,), minutes=30, source="fake")]
        return []

    async def close(self):
        pass


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        trip_api, "rail_hint",
        lambda district, hospital: RailHint(HOME_STATIONS["gaya"], arrival_stations("TMH-MUM")),
    )
    with TestClient(create_app()) as c:
        yield c


def _patient(client):
    return client.app.state.container.cohort.patients[0]


def _ask(client, routes, **params):
    client.app.state.container.routes = routes
    pid = _patient(client).id
    return client.get(f"/api/patients/{pid}/trip/options", params=params)


def test_a_long_road_with_no_public_way_points_to_a_train(client):
    body = _ask(client, FakeRoutes()).json()

    rail = body["rail"]
    assert (rail["from"]["code"], rail["to"]["code"]) == ("GAYA", "CSMT")
    assert [s["code"] for s in rail["also"]] == ["DR", "LTT"]
    assert rail["allow_days"] == 2
    assert rail["irctc_url"].startswith("https://www.irctc.co.in/")
    assert "intercity_rail_not_covered" in body["notes"]


def test_it_never_claims_a_train_a_time_or_a_fare(client):
    rail = _ask(client, FakeRoutes()).json()["rail"]

    assert not {"train", "trains", "fare", "fare_paise", "departs", "number"} & set(rail)


def test_a_short_road_gets_no_train_advice(client):
    body = _ask(client, FakeRoutes(drive_minutes=180)).json()

    assert body["rail"] is None


def test_when_a_route_service_finds_a_public_way_there_is_no_rail_block(client):
    body = _ask(client, FakeRoutes(transit=True)).json()

    assert body["rail"] is None and body["notes"] == []


def test_the_last_leg_starts_from_the_nearest_terminal_when_no_place_is_typed(client):
    routes = FakeRoutes(transit=True)

    body = _ask(client, routes, leg="near").json()

    assert body["origin_used"] == "Mumbai CSMT"
    assert routes.asked[0][0] == "Chhatrapati Shivaji Maharaj Terminus, Mumbai"


def test_a_place_the_family_typed_is_used_as_typed(client):
    routes = FakeRoutes(transit=True)

    body = _ask(client, routes, leg="near", origin="Dadar").json()

    assert body["origin_used"] is None and routes.asked[0][0] == "Dadar"


def test_an_unknown_district_or_hospital_gets_no_rail_guidance():
    assert rail_hint("Nowhere", "TMH-MUM") is None
    assert rail_hint("Gaya", "NO-SUCH-HOSPITAL") is None
    assert rail_hint("Gaya", "TMH-MUM").nearest.code == "CSMT"


# ---- the family's own budget, for the month they travel in


def _limit(client, rupees):
    pid = _patient(client).id
    body = {"amount": rupees, "said": "about three thousand"}
    return client.put(f"/api/patients/{pid}/kharcha/limit", json=body)


def test_with_no_limit_and_no_fare_said_there_is_no_budget_to_show(client):
    body = _ask(client, FakeRoutes()).json()

    assert body["budget"] is None


def test_a_stated_limit_comes_back_with_the_room_left_and_their_words(client):
    assert _limit(client, 3000).status_code == 200

    budget = _ask(client, FakeRoutes()).json()["budget"]

    assert budget["limit_paise"] == 300000
    assert budget["said"] == "about three thousand"
    assert budget["room_paise"] == 300000 - budget["committed_paise"]
    assert budget["stated_fare_paise"] is None


def test_the_room_feeds_the_ranking_not_only_the_screen(client):
    _limit(client, 3000)

    body = _ask(client, FakeRoutes(transit=True), leg="near", origin="Dadar").json()

    assert body["guidance"]["room_paise"] == body["budget"]["room_paise"]


def test_a_fare_the_family_said_is_shown_with_the_sentence_it_came_from(client):
    from saathi.domain.requests import PatientRequest, RequestIntent, TravelFacts

    state = client.app.state.container
    pid = _patient(client).id
    _limit(client, 3000)
    state.runner.requests[pid] = [
        PatientRequest(
            id="r1", patient_id=pid, raw_text="tickets will be 900",
            intent=RequestIntent.MOVE_VISIT,
            travel=TravelFacts(stated_cost_inr=900, stated_in="tickets will be 900"),
        )
    ]

    budget = _ask(client, FakeRoutes()).json()["budget"]

    assert budget["stated_fare_paise"] == 90000
    assert budget["stated_in"] == "tickets will be 900"


def test_a_fare_with_no_sentence_behind_it_is_not_used(client):
    from saathi.domain.requests import PatientRequest, RequestIntent, TravelFacts

    state = client.app.state.container
    pid = _patient(client).id
    state.runner.requests[pid] = [
        PatientRequest(
            id="r1", patient_id=pid, raw_text="ok", intent=RequestIntent.MOVE_VISIT,
            travel=TravelFacts(stated_cost_inr=900),
        )
    ]

    assert _ask(client, FakeRoutes()).json()["budget"] is None
