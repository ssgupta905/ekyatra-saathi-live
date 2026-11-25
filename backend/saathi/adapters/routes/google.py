"""Google's Routes API: which bus, boarded where, leaving when.

The older Directions API is closed to new Google Cloud projects, so this reads
its replacement (`routes.googleapis.com`, computeRoutes). It carries line names,
boarding stops and departure times for Indian cities, and needs a key with
billing enabled, held in the server's environment and never sent to a phone or
written to a log.

What it does not have, and the screen must not pretend it does: reserved long
distance trains (IRCTC publishes no open API) and, for most of India, fares.
A fare is taken only when the response carries one.

The origin a family types for the last leg goes to Google for that one request
and is not stored here.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

import httpx

from ...domain.itinerary import FareBasis, RouteOption, Step, StepMode
from ...ports.routes import Place, RoutesUnavailable

logger = logging.getLogger(__name__)

_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

#: Only what is read, so nothing else is billed for.
_FIELDS = ",".join(
    [
        "routes.duration",
        "routes.legs.steps.travelMode",
        "routes.legs.steps.staticDuration",
        "routes.legs.steps.distanceMeters",
        "routes.legs.steps.navigationInstruction.instructions",
        "routes.legs.steps.transitDetails",
        "routes.travelAdvisory.transitFare",
    ]
)

_VEHICLE = {
    "BUS": StepMode.BUS,
    "INTERCITY_BUS": StepMode.BUS,
    "TROLLEYBUS": StepMode.BUS,
    "SHARE_TAXI": StepMode.TAXI,
    "SUBWAY": StepMode.METRO,
    "METRO_RAIL": StepMode.METRO,
    "MONORAIL": StepMode.METRO,
    "HEAVY_RAIL": StepMode.TRAIN,
    "COMMUTER_TRAIN": StepMode.TRAIN,
    "HIGH_SPEED_TRAIN": StepMode.TRAIN,
    "LONG_DISTANCE_TRAIN": StepMode.TRAIN,
    "RAIL": StepMode.TRAIN,
    "TRAM": StepMode.TRAM,
    "FERRY": StepMode.FERRY,
}


def _seconds(text: str | None) -> int:
    """A protobuf duration, "1234s", as whole seconds."""
    match = re.fullmatch(r"(\d+)(?:\.\d+)?s", text or "")
    return int(match.group(1)) if match else 0


def _minutes(text: str | None) -> int:
    return round(_seconds(text) / 60)


def _when(text: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")) if text else None
    except ValueError:
        return None


def _step(raw: dict) -> Step:
    minutes = _minutes(raw.get("staticDuration"))
    metres = raw.get("distanceMeters")
    transit = raw.get("transitDetails")
    if raw.get("travelMode") == "TRANSIT" and transit:
        stops = transit.get("stopDetails", {})
        line = transit.get("transitLine", {})
        vehicle = (line.get("vehicle") or {}).get("type", "")
        return Step(
            mode=_VEHICLE.get(vehicle, StepMode.OTHER),
            line=line.get("nameShort") or line.get("name"),
            towards=transit.get("headsign"),
            board_at=(stops.get("departureStop") or {}).get("name"),
            get_off_at=(stops.get("arrivalStop") or {}).get("name"),
            stops=transit.get("stopCount"),
            departs=_when(stops.get("departureTime")),
            arrives=_when(stops.get("arrivalTime")),
            minutes=minutes,
        )
    walking = raw.get("travelMode") == "WALK"
    return Step(
        mode=StepMode.WALK if walking else StepMode.TAXI,
        minutes=minutes,
        metres=metres,
        note=((raw.get("navigationInstruction") or {}).get("instructions") if walking else None),
    )


def _fare_paise(route: dict) -> int | None:
    fare = (route.get("travelAdvisory") or {}).get("transitFare") or {}
    if fare.get("currencyCode") != "INR":
        return None
    rupees = int(fare.get("units", 0)) + int(fare.get("nanos", 0)) / 1e9
    return round(rupees * 100) if rupees > 0 else None


def parse(body: dict) -> list[RouteOption]:
    """A Routes response as options. Public so a recorded response can be tested."""
    found: list[RouteOption] = []
    for number, route in enumerate(body.get("routes", [])):
        legs = route.get("legs") or []
        if not legs:
            continue
        steps = tuple(_step(s) for leg in legs for s in leg.get("steps", []))
        timed = [s for s in steps if s.departs]
        paise = _fare_paise(route)
        found.append(
            RouteOption(
                id=f"google-{number}",
                steps=steps,
                minutes=_minutes(route.get("duration")),
                departs=timed[0].departs if timed else None,
                arrives=timed[-1].arrives if timed else None,
                fare_paise=paise,
                fare_basis=FareBasis.SERVICE if paise else FareBasis.NONE,
                source="google",
            )
        )
    return found


def _place(place: Place) -> dict:
    lat, _, lng = place.text.partition(",")
    try:
        return {"location": {"latLng": {"latitude": float(lat), "longitude": float(lng)}}}
    except ValueError:
        return {"address": place.text}


class GoogleRoutes:
    name = "google"

    def __init__(self, api_key: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.AsyncClient(timeout=15)

    async def options(
        self,
        origin: Place,
        destination: Place,
        *,
        mode: str,
        arrive_by: datetime | None = None,
        depart_at: datetime | None = None,
    ) -> list[RouteOption]:
        body: dict = {
            "origin": _place(origin),
            "destination": _place(destination),
            "travelMode": "TRANSIT" if mode == "transit" else "DRIVE",
            "regionCode": "IN",
        }
        if mode == "transit":
            if arrive_by is not None:
                body["arrivalTime"] = arrive_by.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            elif depart_at is not None:
                body["departureTime"] = depart_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            body["computeAlternativeRoutes"] = False
        try:
            response = await self._client.post(
                _URL, json=body, headers={"X-Goog-Api-Key": self._key, "X-Goog-FieldMask": _FIELDS}
            )
        except httpx.HTTPError:
            # The exception text can carry the request; say only what failed.
            raise RoutesUnavailable("the route service could not be reached") from None
        if response.status_code == 404 or (response.status_code == 200 and not response.json()):
            return []
        if response.status_code != 200:
            logger.warning("routes refused: HTTP %s", response.status_code)
            raise RoutesUnavailable(f"the route service said {response.status_code}")
        options = parse(response.json())
        if mode == "driving":
            # A car or taxi: the route service gives no price and none is made up.
            options = [
                o.model_copy(
                    update={
                        "steps": tuple(
                            s.model_copy(update={"mode": StepMode.TAXI})
                            if s.mode is not StepMode.WALK
                            else s
                            for s in o.steps
                        )
                    }
                )
                for o in options
            ]
        return options

    async def close(self) -> None:
        await self._client.aclose()
