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
