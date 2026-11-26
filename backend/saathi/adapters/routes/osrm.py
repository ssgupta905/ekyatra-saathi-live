"""Driving routes from OSRM, which this project already trusts and already runs.

`tools/geo.py` has asked OSRM how far and how long a journey is since the
beginning — it is what produces "Darbhanga to Mumbai: about 1,886 km, roughly
22 hours by road". OSRM is a routing engine; answering that question is the
smaller half of what it does. This adapter asks it the other half, so the
family's screen can show a route and a map rather than a number.

**Why this exists when there is already a Google adapter.** Google's Routes API
is better: it has buses, boarding stops, departure times. It also needs a key
with billing enabled, and without one the route port has no implementation at
all — `trip/options` answers "no route service is set up here" and the in-app
map has nothing to draw. OSRM's public server needs no key, so a deployment
with no billing account still gets real routes instead of none.

**What it cannot do, and does not pretend to.** OSRM has no timetables. There
is no bus, no train, no departure time, and `transit` returns nothing at all
rather than a car route wearing a bus's clothes — the port says "Empty when
there is no way", and a family told to catch a bus that does not exist is
worse served than one told we do not know. For the same reason no fare is ever
attached: `FareBasis.NONE`, because OSRM has no idea what a journey costs and
this project does not report a fare it was not given.

So: one driving option, with the real distance and the real duration, from the
same service that already answers for the journey time on every plan.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import httpx

from ...domain.itinerary import FareBasis, RouteOption, Step, StepMode
from ...ports.routes import Place, RoutesUnavailable

logger = logging.getLogger(__name__)

#: The public demo server. Fine for a pilot and explicitly not for volume —
#: it asks for no key and gives no guarantee. A deployment that depends on it
#: should run its own; the address is configuration for that reason.
DEFAULT_ROUTER = "https://router.project-osrm.org"


def _coordinates(place: Place) -> str | None:
    """OSRM speaks in `lng,lat` and nothing else.

    A place a person typed is not a coordinate, and this adapter does not
    geocode: that is a second service, a second failure mode, and a second
    thing to get wrong silently. `trip_options` already resolves a family's
    origin before it asks, so by here a free-text place means somebody has
    passed something this cannot route and should be told.
    """
    text = (place.text or "").strip()
    if "," not in text:
        return None
    lat_text, _, lng_text = text.partition(",")
    try:
        lat, lng = float(lat_text), float(lng_text)
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return f"{lng},{lat}"


class OsrmRoutes:
    """The driving half of the route port, from OSRM."""

    name = "osrm"

    def __init__(self, base_url: str = DEFAULT_ROUTER, *, timeout: float = 12.0) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": "ekyatra-saathi/1.0 (care logistics; contact: ops@ekyatra.in)"},
        )

    async def options(
        self,
        origin: Place,
        destination: Place,
        *,
        mode: str,
        arrive_by: datetime | None = None,
        depart_at: datetime | None = None,
    ) -> list[RouteOption]:
        if mode != "driving":
            # No timetables here. Saying so by returning nothing is the whole
            # point; the caller then offers Maps rather than a made-up bus.
            return []

        start, end = _coordinates(origin), _coordinates(destination)
        if start is None or end is None:
            raise RoutesUnavailable(
                "OSRM routes by coordinate; one of these is a place name: "
                f"{origin.text!r} -> {destination.text!r}"
            )

        url = f"{self._base}/route/v1/driving/{start};{end}"
        try:
            response = await self._client.get(
                url, params={"overview": "false", "alternatives": "false"}
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise RoutesUnavailable(f"osrm: {exc}") from exc
        except ValueError as exc:
            raise RoutesUnavailable(f"osrm returned something that is not json: {exc}") from exc

        if payload.get("code") != "Ok" or not payload.get("routes"):
            # "NoRoute" is an answer, not a failure: there is no road.
            logger.info("osrm found no driving route: %s", payload.get("code"))
            return []

        route = payload["routes"][0]
        try:
            seconds = float(route["duration"])
            metres = float(route["distance"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RoutesUnavailable(f"osrm route has no duration or distance: {exc}") from exc

        minutes = max(int(round(seconds / 60.0)), 0)
        departs = depart_at
        if departs is None and arrive_by is not None:
            departs = arrive_by - timedelta(minutes=minutes)
        arrives = arrive_by or (departs + timedelta(minutes=minutes) if departs else None)

        return [
            RouteOption(
                id=f"osrm:{start}->{end}",
                steps=(
                    Step(
                        mode=StepMode.TAXI,
                        minutes=minutes,
                        metres=int(round(metres)),
                        departs=departs,
                        arrives=arrives,
                        note="By road. OSRM has no timetables, so no bus or train is offered here.",
                    ),
                ),
                minutes=minutes,
                departs=departs,
                arrives=arrives,
                # OSRM knows the road and nothing about what using it costs.
                fare_paise=None,
                fare_basis=FareBasis.NONE,
                source=self.name,
            )
        ]

    async def close(self) -> None:
        await self._client.aclose()


__all__ = ["DEFAULT_ROUTER", "OsrmRoutes"]
