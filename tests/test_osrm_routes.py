"""Driving routes from OSRM, and the things it must refuse to invent.

The reason this adapter exists is that without it the route port has no
implementation unless somebody has a Google key with billing enabled — and a
deployment without one answers "no route service is set up here" and draws no
map at all. OSRM needs no key and this project already asks it for every
journey time on every plan.

What is pinned here is mostly what it does *not* do. OSRM has no timetables,
so there is no bus, no train and no fare, and the interesting failure is the
one where a car route is quietly dressed as public transport.
"""

from __future__ import annotations

import json

import httpx
import pytest
from saathi.adapters.routes.osrm import OsrmRoutes
from saathi.domain.itinerary import FareBasis, StepMode
from saathi.ports.routes import Place, RoutesUnavailable

DARBHANGA = Place("26.1542,85.8918")
MUMBAI = Place("19.0043,72.8428")


def _server(payload: dict, status: int = 200, seen: list | None = None) -> OsrmRoutes:
    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, text=json.dumps(payload))

    routes = OsrmRoutes()
    routes._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    return routes


ONE_ROUTE = {"code": "Ok", "routes": [{"duration": 78660.0, "distance": 1867000.0}]}


async def test_a_driving_route_carries_the_real_duration_and_distance() -> None:
    routes = _server(ONE_ROUTE)
    try:
        [option] = await routes.options(DARBHANGA, MUMBAI, mode="driving")
    finally:
        await routes.close()

    assert option.minutes == 1311
    assert option.steps[0].metres == 1_867_000
    assert option.source == "osrm"


async def test_transit_gets_nothing_rather_than_a_car_route_in_disguise() -> None:
    """The one that matters. A family told to catch a bus that does not exist
    is worse served than a family told we do not know."""
    routes = _server(ONE_ROUTE)
    try:
        assert await routes.options(DARBHANGA, MUMBAI, mode="transit") == []
    finally:
        await routes.close()


async def test_no_fare_is_ever_attached() -> None:
    """OSRM knows the road and nothing about what using it costs."""
    routes = _server(ONE_ROUTE)
    try:
        [option] = await routes.options(DARBHANGA, MUMBAI, mode="driving")
    finally:
        await routes.close()

    assert option.fare_paise is None
    assert option.fare_basis is FareBasis.NONE


async def test_the_step_is_a_taxi_and_never_a_public_one() -> None:
    routes = _server(ONE_ROUTE)
    try:
        [option] = await routes.options(DARBHANGA, MUMBAI, mode="driving")
    finally:
        await routes.close()

    assert option.steps[0].mode is StepMode.TAXI
    assert not option.is_public, "a road route must not count as public transport"


async def test_no_road_is_an_answer_not_a_failure() -> None:
    routes = _server({"code": "NoRoute", "routes": []})
    try:
        assert await routes.options(DARBHANGA, MUMBAI, mode="driving") == []
    finally:
        await routes.close()


async def test_a_place_name_is_refused_rather_than_guessed_at() -> None:
    """This adapter does not geocode. Somebody passing free text has passed
    something it cannot route, and should be told rather than quietly given
    a route between two places nobody chose."""
    routes = _server(ONE_ROUTE)
    try:
        with pytest.raises(RoutesUnavailable, match="place name"):
            await routes.options(Place("Darbhanga"), MUMBAI, mode="driving")
    finally:
        await routes.close()


async def test_an_unreachable_router_is_reported_not_swallowed() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    routes = OsrmRoutes()
    routes._client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    try:
        with pytest.raises(RoutesUnavailable, match="osrm"):
            await routes.options(DARBHANGA, MUMBAI, mode="driving")
    finally:
        await routes.close()


async def test_it_asks_osrm_in_lng_lat_order() -> None:
    """Latitude first is the commonest way to get a route to the wrong
    continent, and OSRM will happily answer for it."""
    seen: list[httpx.Request] = []
    routes = _server(ONE_ROUTE, seen=seen)
    try:
        await routes.options(DARBHANGA, MUMBAI, mode="driving")
    finally:
        await routes.close()

    assert "85.8918,26.1542;72.8428,19.0043" in str(seen[0].url)
