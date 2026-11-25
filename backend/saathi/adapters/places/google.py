"""Google's Places API (New): what is around a point.

Text Search with a location bias, asking only for the fields read (so only
those are billed). Needs the same server-held key as the route planner, never
sent to a phone. Only generic words go to Google ("pharmacy", "Jan Aushadhi
Kendra"); nothing about the family or their condition.

Ratings and reviews are deliberately not requested: they must never decide
where a patient is sent.
"""

from __future__ import annotations

import logging
from datetime import time

import httpx

from ...domain.places import Period, Place, PlaceKind
from ...ports.places import PlacesUnavailable

logger = logging.getLogger(__name__)

_URL = "https://places.googleapis.com/v1/places:searchText"

_FIELDS = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.nationalPhoneNumber",
        "places.googleMapsUri",
        "places.businessStatus",
        "places.currentOpeningHours.openNow",
        "places.regularOpeningHours.periods",
    ]
)

#: Generic words only. `type` narrows where the service has one.
_QUERY: dict[PlaceKind, tuple[str, str | None]] = {
    PlaceKind.PHARMACY: ("pharmacy medical store", "pharmacy"),
    PlaceKind.JAN_AUSHADHI: ("Jan Aushadhi Kendra", None),
    PlaceKind.LAB: ("diagnostic laboratory pathology lab", None),
    PlaceKind.EQUIPMENT: (
        "medical equipment wheelchair oxygen concentrator surgical appliances",
        None,
    ),
    PlaceKind.CLINIC: ("clinic", "doctor"),
    PlaceKind.PHYSIO: ("physiotherapy clinic", "physiotherapist"),
}

_LANGUAGE = {"hi": "hi", "bn": "bn", "or": "or", "ta": "ta", "en": "en"}


def _time(block: dict | None) -> time | None:
    if not block:
        return None
    return time(int(block.get("hour", 0)), int(block.get("minute", 0)))


def _periods(raw: dict | None) -> tuple[Period, ...]:
    found = []
    for p in (raw or {}).get("periods", []):
        opens = p.get("open") or {}
        closes = p.get("close")
        if "day" not in opens:
            continue
        found.append(
            Period(
                open_day=opens["day"],
                open_at=_time(opens) or time(0, 0),
                close_day=(closes or {}).get("day"),
                close_at=_time(closes),
            )
        )
    return tuple(found)


def parse(body: dict, kind: PlaceKind) -> list[Place]:
    """A Text Search response as places. Public so a recorded response can be tested."""
    found: list[Place] = []
    for raw in body.get("places", []):
        if raw.get("businessStatus") not in (None, "OPERATIONAL"):
            continue  # closed for good or temporarily: not somewhere to send a family
        where = raw.get("location") or {}
        if "latitude" not in where:
            continue
        found.append(
            Place(
                id=raw["id"],
                name=(raw.get("displayName") or {}).get("text", ""),
                kind=kind,
                address=raw.get("formattedAddress", ""),
                latitude=where["latitude"],
                longitude=where["longitude"],
                phone=raw.get("nationalPhoneNumber"),
                open_now=(raw.get("currentOpeningHours") or {}).get("openNow"),
                periods=_periods(raw.get("regularOpeningHours")),
                maps_uri=raw.get("googleMapsUri"),
                source="google",
            )
        )
    return found


class GooglePlaces:
    name = "google"

    def __init__(self, api_key: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.AsyncClient(timeout=15)

    async def nearby(
        self,
        kind: PlaceKind,
        latitude: float,
        longitude: float,
        *,
        radius_m: int = 3000,
        language: str = "en",
    ) -> list[Place]:
        text, included = _QUERY[kind]
        body: dict = {
            "textQuery": text,
            "languageCode": _LANGUAGE.get(language, "en"),
            "regionCode": "IN",
            "pageSize": 10,
            # A bias, not a limit: a village with one shop still gets it.
            "locationBias": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": float(radius_m),
                }
            },
        }
        if included:
            body["includedType"] = included
        try:
            response = await self._client.post(
                _URL, json=body, headers={"X-Goog-Api-Key": self._key, "X-Goog-FieldMask": _FIELDS}
            )
        except httpx.HTTPError:
            raise PlacesUnavailable("the map service could not be reached") from None
        if response.status_code != 200:
            logger.warning("places refused: HTTP %s", response.status_code)
            raise PlacesUnavailable(f"the map service said {response.status_code}")
        return parse(response.json(), kind)

    async def close(self) -> None:
        await self._client.aclose()
