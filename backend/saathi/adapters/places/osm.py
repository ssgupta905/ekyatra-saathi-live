"""OpenStreetMap, through the Overpass API: real shops, labs and clinics, no key.

What it knows is what OpenStreetMap's volunteers have mapped, so coverage and
freshness vary by town and the screen says "call to check". Names, phones and
opening hours are present only where a mapper added them; a place with no hours
is shown as "hours not known", never as open.

Only a point and a generic category go out (no name, no condition, nothing
about the family). Results are kept in memory for hours per (category, ~1 km
cell) so a busy day does not hammer a free public service. The data is
© OpenStreetMap contributors (ODbL); the screen shows that credit.
"""

from __future__ import annotations

import logging
import re
import time as clock
from datetime import time

import httpx

from ...domain.places import Period, Place, PlaceKind
from ...ports.places import PlacesUnavailable

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://overpass-api.de/api/interpreter"
#: Public mirrors tried in turn when the first is busy (it often is).
MIRRORS = (
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
#: Shops and their hours change slowly, and a free public service is slow.
_KEEP_SECONDS = 12 * 3600

#: Overpass selectors per kind. `name~` matches are case-insensitive.
_SELECT: dict[PlaceKind, list[str]] = {
    PlaceKind.PHARMACY: ['["amenity"="pharmacy"]'],
    PlaceKind.JAN_AUSHADHI: ['["name"~"jan ?aushadhi|janaushadhi|jan ?aushadi",i]', '["brand"~"jan ?aushadhi",i]'],
    PlaceKind.LAB: ['["healthcare"="laboratory"]', '["name"~"diagnostic|patholog|laborator",i]["amenity"~"clinic|doctors"]'],
    PlaceKind.EQUIPMENT: ['["shop"="medical_supply"]'],
    PlaceKind.CLINIC: ['["amenity"~"^(clinic|doctors)$"]'],
    PlaceKind.PHYSIO: ['["healthcare"="physiotherapist"]'],
}

_DAYS = {"Mo": 1, "Tu": 2, "We": 3, "Th": 4, "Fr": 5, "Sa": 6, "Su": 0}  # Sunday = 0, as Place expects
_ORDER = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]


def _hhmm(text: str) -> time | None:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", text.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h == 24 and mi == 0:
        return time(0, 0)
    return time(h, mi) if h < 24 and mi < 60 else None


def _days(spec: str) -> list[int] | None:
    """"Mo-Sa", "Mo,We,Fr", "Mo-Fr,Su" as day numbers (Sunday = 0). None if not understood."""
    found: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, _, b = part.partition("-")
            if a not in _DAYS or b not in _DAYS:
                return None
            i, j = _ORDER.index(a), _ORDER.index(b)
            span = _ORDER[i : j + 1] if i <= j else _ORDER[i:] + _ORDER[: j + 1]
            found += [_DAYS[d] for d in span]
        elif part in _DAYS:
            found.append(_DAYS[part])
        else:
            return None
    return found


def parse_opening_hours(text: str | None) -> tuple[Period, ...]:
    """The common shapes of OpenStreetMap's `opening_hours`. Anything stranger is "not known".

    Understood: "24/7", "Mo-Sa 09:00-21:00; Su off", "09:00-21:00" (every day),
    several spans in a day ("09:00-13:00,16:00-21:00"), spans past midnight.
    Not understood (and so not guessed): holidays, months, "sunrise", comments.
    """
    if not text:
        return ()
    text = text.strip()
    if text == "24/7":
        return (Period(open_day=0, open_at=time(0)),)
    periods: list[Period] = []
    for rule in (r.strip() for r in text.split(";") if r.strip()):
        m = re.fullmatch(r"(?:(?P<days>[A-Za-z,\-]+)\s+)?(?P<rest>off|[0-9:,\-\s]+)", rule)
        if not m:
            return ()
        days = list(range(7)) if not m["days"] else _days(m["days"])
        if days is None:
            return ()
        if m["rest"].strip() == "off":
            periods = [p for p in periods if p.open_day not in days]
            continue
        for span in m["rest"].split(","):
            a, _, b = span.strip().partition("-")
            start, end = _hhmm(a), _hhmm(b)
            if start is None or end is None:
                return ()
            for d in days:
                if end > start:
                    periods.append(Period(open_day=d, open_at=start, close_day=d, close_at=end))
                else:  # past midnight, or midnight itself
                    periods.append(Period(open_day=d, open_at=start, close_day=(d + 1) % 7, close_at=end))
    return tuple(periods)


def _address(tags: dict) -> str:
    if tags.get("addr:full"):
        return tags["addr:full"]
    street = " ".join(x for x in (tags.get("addr:housenumber"), tags.get("addr:street")) if x)
    parts = [street, tags.get("addr:suburb"), tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village")]
    return ", ".join(p for p in parts if p)


def parse(body: dict, kind: PlaceKind) -> list[Place]:
    """An Overpass response as places. Public so a recorded response can be tested."""
    found: list[Place] = []
    for el in body.get("elements", []):
        tags = el.get("tags") or {}
        where = el if "lat" in el else el.get("center") or {}
        name = tags.get("name") or tags.get("name:en")
        if not name or "lat" not in where:
            continue  # nobody can be sent to a place with no name or no position
        found.append(
            Place(
                id=f"osm-{el.get('type', 'node')}-{el['id']}",
                name=name,
                kind=kind,
                address=_address(tags),
                latitude=where["lat"],
                longitude=where["lon"],
                phone=tags.get("phone") or tags.get("contact:phone") or tags.get("mobile") or tags.get("contact:mobile"),
                periods=parse_opening_hours(tags.get("opening_hours")),
                source="osm",
            )
        )
    return found


def _query(kind: PlaceKind, lat: float, lon: float, radius_m: int) -> str:
    around = f"(around:{radius_m},{lat},{lon})"
    body = "".join(f"nwr{sel}{around};" for sel in _SELECT[kind])
    return f"[out:json][timeout:25];({body});out center tags 40;"


class OsmPlaces:
    name = "osm"

    def __init__(self, url: str = DEFAULT_URL, *, client: httpx.AsyncClient | None = None) -> None:
        self._urls = (url, *[m for m in MIRRORS if m != url])
        # An honest, generic identity: the public service asks for one. No contact details.
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(45, connect=6), headers={"User-Agent": "saathi-care-navigator/1.0 (open-data lookup)"}
        )
        self._kept: dict[tuple, tuple[float, list[Place]]] = {}

    async def nearby(
        self, kind: PlaceKind, latitude: float, longitude: float, *, radius_m: int = 3000, language: str = "en"
    ) -> list[Place]:
        cell = (kind, round(latitude, 2), round(longitude, 2), radius_m)
        hit = self._kept.get(cell)
        if hit and clock.monotonic() - hit[0] < _KEEP_SECONDS:
            return hit[1]
        response = None
        for url in self._urls:
            try:
                response = await self._client.post(url, data={"data": _query(kind, latitude, longitude, radius_m)})
            except httpx.HTTPError:
                continue
            if response.status_code == 200:
                break
            logger.warning("overpass mirror refused: HTTP %s", response.status_code)
        if response is None or response.status_code != 200:
            raise PlacesUnavailable("the map data service could not be reached")
        try:
            places = parse(response.json(), kind)
        except ValueError:
            raise PlacesUnavailable("the map data service sent something unreadable") from None
        self._kept[cell] = (clock.monotonic(), places)
        return places

    async def warm(self, points: list[tuple[float, float]], *, pause: float = 3.0) -> None:
        """Fill the cache for places families will ask about (hospital doors), politely, one at a time.

        A free public service can take half a minute to answer; a family should
        not be the one who waits for it. Failures are ignored: the first real
        request simply asks again.
        """
        import asyncio

        failures = 0
        for lat, lon in points:
            for kind in PlaceKind:
                try:
                    await self.nearby(kind, lat, lon)
                    failures = 0
                except PlacesUnavailable:
                    failures += 1
                    if failures >= 2:
                        # The service is struggling. Leaving it alone is the polite thing.
                        logger.info("overpass is busy; not warming further now")
                        return
                await asyncio.sleep(pause)

    async def close(self) -> None:
        await self._client.aclose()
