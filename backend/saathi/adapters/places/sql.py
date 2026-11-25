"""Healthcare places read from our own table instead of a public server.

The live reader (`osm.py`) talks to Overpass, which is free, open, and — on
the public endpoints — overloaded. Measured while building this: thirty to
forty seconds for an answer, and 502s often enough that the adapter has three
mirrors to fall through. A family who taps "Near you" and waits forty seconds
has been told the feature does not work.

So the same data is loaded monthly into a table and read from there. That
costs a loader and a scheduled job, and buys an answer in milliseconds that
cannot be taken away by somebody else's server being busy on the day.

**Why the parsing is shared rather than copied.** `opening_hours` is stored
exactly as OpenStreetMap writes it, and parsed by `osm.parse_opening_hours`
— the same function the live reader uses. Two parsers for one format drift,
and the day they disagree is the day a family is told a shop is open when it
is closed.

**Why the distance filter is a box and then a circle.** The index is on
`(kind, latitude, longitude)`, so a bounding box is the part the database can
do quickly. A box drawn around a 3 km radius includes corners up to 4.2 km
away, so the exact radius is applied in Python afterwards. Doing it the other
way — a true distance in SQL — means no index and a full scan of every
pharmacy in India.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from ...db.tables import PlaceRow
from ...domain.places import Place, PlaceKind
from ...ports.places import PlacesUnavailable
from .osm import parse_opening_hours

logger = logging.getLogger(__name__)

#: Metres per degree of latitude. Constant enough anywhere on Earth; longitude
#: is not, which is why it is scaled by the cosine of the latitude below.
_METRES_PER_DEGREE = 111_320.0

#: Most a single query will return. The screen shows a handful and a family
#: scrolling past forty pharmacies is not being helped by the forty-first.
_MOST = 40


def _box(latitude: float, longitude: float, radius_m: int) -> tuple[float, float, float, float]:
    """The smallest lat/lon rectangle containing a circle of this radius.

    Longitude degrees shrink towards the poles, so the east-west span is
    divided by `cos(latitude)`. At India's latitudes that is a correction of
    about 15%, which is the difference between finding a pharmacy at the edge
    of the radius and not.

    Clamped near the poles, where the cosine approaches zero and the box would
    otherwise widen to the whole world. Nobody in this project is at 89°, but
    a division that can produce infinity should not be left to trust.
    """
    span_lat = radius_m / _METRES_PER_DEGREE
    cos = max(math.cos(math.radians(latitude)), 0.01)
    span_lon = radius_m / (_METRES_PER_DEGREE * cos)
    return (
        latitude - span_lat,
        latitude + span_lat,
        longitude - span_lon,
        longitude + span_lon,
    )


def metres_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line metres between two points.

    Equirectangular rather than haversine: over the few kilometres this is
    ever asked about the difference is centimetres, and the result is shown
    to a family rounded to the nearest hundred metres as "a rough guide".
    """
    mean_lat = math.radians((lat1 + lat2) / 2)
    dx = math.radians(lon2 - lon1) * math.cos(mean_lat)
    dy = math.radians(lat2 - lat1)
    return math.hypot(dx, dy) * 6_371_000


class SqlPlaces:
    """`PlaceFinder` over the `places` table.

    Takes a URL and owns a synchronous engine, which is how every other
    records-database adapter here works (`adapters/spends/sql.py`). The port
    is async, so the one query is run in a thread rather than opening a
    second, asynchronous engine against the same SQLite file — two engines on
    one file is how you get a database lock on a laptop five minutes before a
    demo.
    """

    name = "local"

    def __init__(self, url: str) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self._engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)

    async def nearby(
        self,
        kind: PlaceKind,
        latitude: float,
        longitude: float,
        *,
        radius_m: int = 3000,
        language: str = "en",
    ) -> list[Place]:
        """Places of this kind within the radius, nearest first.

        `language` is accepted and ignored: these are names as the people who
        mapped them wrote them, and this adapter has nothing to translate them
        with. Pretending otherwise by taking the argument and silently doing
        nothing would be worse than saying so here.
        """
        del language

        south, north, west, east = _box(latitude, longitude, radius_m)
        try:
            rows = await asyncio.to_thread(self._read, kind, south, north, west, east)
        except Exception as exc:  # noqa: BLE001 — the port's contract is one error
            # The same failure the live reader raises, so callers have one
            # thing to handle and the screen says "could not load" either way.
            raise PlacesUnavailable(f"could not read the places table: {exc}") from exc

        found: list[tuple[float, Place]] = []
        for row in rows:
            metres = metres_between(latitude, longitude, row.latitude, row.longitude)
            if metres > radius_m:
                continue  # inside the box, outside the circle
            found.append((metres, _place(row)))

        found.sort(key=lambda pair: pair[0])
        return [place for _, place in found[:_MOST]]

    def _read(self, kind, south, north, west, east) -> list[PlaceRow]:
        with self._sessions() as session:
            return list(
                session.execute(
                    select(PlaceRow)
                    .where(
                        PlaceRow.kind == kind.value,
                        PlaceRow.latitude.between(south, north),
                        PlaceRow.longitude.between(west, east),
                    )
                    # A generous ceiling on the box, before the circle trims
                    # it. Without one, a query centred on a dense city reads
                    # thousands of rows to show six.
                    .limit(_MOST * 8)
                ).scalars()
            )

    async def close(self) -> None:
        self._engine.dispose()


def _place(row: PlaceRow) -> Place:
    return Place(
        id=row.id,
        name=row.name or "",
        kind=PlaceKind(row.kind),
        address=row.address or "",
        latitude=row.latitude,
        longitude=row.longitude,
        phone=row.phone,
        # Deliberately not computed here. `open_now` means "open at the
        # instant the map service was asked", and this table was last written
        # weeks ago — answering it would be asserting something about now from
        # something that was true in October. The periods are given instead
        # and `Place.open_at` answers for whatever moment the caller means.
        open_now=None,
        periods=parse_opening_hours(row.opening_hours),
        maps_uri=f"https://www.openstreetmap.org/{row.id}",
        source="osm-local",
    )


def place_row(
    *,
    osm_id: str,
    kind: PlaceKind,
    name: str,
    address: str,
    latitude: float,
    longitude: float,
    phone: str | None,
    opening_hours: str | None,
    loaded_at: datetime,
) -> dict:
    """One row as the loader writes it, so the loader and reader agree.

    A plain dict rather than a `PlaceRow`, because the loader upserts in bulk
    and never wants instances.
    """
    return {
        "id": osm_id,
        "kind": kind.value,
        "name": (name or "")[:200],
        "address": (address or "")[:300],
        "latitude": latitude,
        "longitude": longitude,
        "phone": (phone or None) and phone[:40],
        "opening_hours": (opening_hours or None) and opening_hours[:300],
        "loaded_at": loaded_at,
    }


__all__ = ["SqlPlaces", "metres_between", "place_row"]
