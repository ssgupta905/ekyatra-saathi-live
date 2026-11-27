"""Load healthcare places from OpenStreetMap into our own table.

    python -m saathi.tools.load_places places.geojson          # say what it would do
    python -m saathi.tools.load_places places.geojson --write

**Where the file comes from.** Not from here: the India extract is 1.7 GB and
almost none of it is about health. Filter it wherever there is disk — a
laptop, or the scheduled job in `.github/workflows/` — and feed this the
result:

    wget https://download.geofabrik.de/asia/india-latest.osm.pbf
    osmium tags-filter india-latest.osm.pbf \\
        amenity=pharmacy,clinic,doctors healthcare shop=medical_supply \\
        -o health.osm.pbf
    osmium export health.osm.pbf -f geojson -o places.geojson

That leaves roughly a hundred megabytes, which fits a free Postgres tier.

**Upsert by OpenStreetMap's id, never insert.** A monthly reload must update
the pharmacy that moved and leave the one that did not, and a loader that
inserted would double the table every month. The id carries the element type
("node/123456789") because OSM's node, way and relation ids are separate
sequences and collide with each other otherwise.

**Nothing is deleted.** A place missing from this month's extract is more
often a mapping edit than a closed shop, and removing it would silently drop
a pharmacy a family used last week. `loaded_at` records when each row was
last seen, so staleness is visible and can be acted on deliberately.

**No ratings, ever.** The filter below does not read them, the table has no
column for them, and `tests/test_sql_places.py` fails if one appears.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import sessionmaker

from ..adapters.places.sql import place_row
from ..config import get_settings
from ..db.tables import PlaceRow
from ..domain.places import PlaceKind

logger = logging.getLogger(__name__)

#: Which OpenStreetMap tags make a place each kind. The same intent as the
#: Overpass selectors in `adapters/places/osm.py`, expressed against a
#: feature's tags rather than as a query — they are checked against each other
#: in `tests/test_sql_places.py`, because two definitions of "pharmacy" that
#: disagree is a family sent to the wrong shop.
#: `\s*` and not `\s?`: real entries carry "Jan  Aushadhi" with two spaces,
#: "JanAushadhi" with none, and both spellings of the last syllable. A single
#: optional space missed a third of the ones in the extract, and each miss is
#: a government generic-medicine shop a family is never offered.
_JAN_AUSHADHI = re.compile(r"jan\s*aushadh?i", re.I)


#: What a charitable guest house beside an Indian hospital is actually called.
#: Trust/sadan/bhavan are the commonest; `yatri niwas` is the railways' word
#: and shows up near stations. Matched on the name because OSM has no tag for
#: any of it.
_DHARAMSHALA = re.compile(
    r"dharam\s?shala|dharmashala|dharamsala|yatri\s?niwas|yatri\s?nivas"
    r"|musafir\s?khana|sarai|seva\s?sadan|trust\s+(?:bhavan|bhawan|guest)"
    r"|charitable\s+(?:trust|guest)",
    re.I,
)


def kind_of(tags: dict) -> PlaceKind | None:
    """What kind of place this is, or None if it is not one we show.

    Order matters: a Jan Aushadhi store is also `amenity=pharmacy`, and it is
    the more useful answer — they are government generic-medicine shops and
    cheaper, which is why `KINDS_FOR_NEED` offers them first when money is
    tight. Checking pharmacy first would hide every one of them.
    """
    amenity = (tags.get("amenity") or "").lower()
    healthcare = (tags.get("healthcare") or "").lower()
    shop = (tags.get("shop") or "").lower()
    name = tags.get("name") or ""
    brand = tags.get("brand") or ""

    if _JAN_AUSHADHI.search(name) or _JAN_AUSHADHI.search(brand):
        return PlaceKind.JAN_AUSHADHI
    if amenity == "pharmacy":
        return PlaceKind.PHARMACY
    if healthcare == "laboratory":
        return PlaceKind.LAB
    if amenity in {"clinic", "doctors"} and re.search(
        r"diagnostic|patholog|laborator", name, re.I
    ):
        return PlaceKind.LAB
    if healthcare == "physiotherapist":
        return PlaceKind.PHYSIO
    if shop == "medical_supply":
        return PlaceKind.EQUIPMENT
    if amenity in {"clinic", "doctors"}:
        return PlaceKind.CLINIC

    # Somewhere to sleep. Checked after the medical kinds so a pharmacy inside
    # a hotel is still a pharmacy.
    tourism = (tags.get("tourism") or "").lower()
    if _DHARAMSHALA.search(name) or _DHARAMSHALA.search(brand):
        # OSM has no tag for this. They are mapped as guest houses, hostels,
        # sometimes `amenity=shelter`, and are recognisable only by what they
        # are called — so the name is the evidence, as it is for Jan Aushadhi.
        return PlaceKind.DHARAMSHALA
    if tourism in {"guest_house", "hostel"}:
        return PlaceKind.GUEST_HOUSE
    if tourism == "hotel":
        return PlaceKind.HOTEL
    return None


def address_of(tags: dict) -> str:
    """The address as OSM holds it, in the order an Indian address is written."""
    parts = [
        tags.get("addr:housenumber"),
        tags.get("addr:street"),
        tags.get("addr:suburb") or tags.get("addr:neighbourhood"),
        tags.get("addr:city"),
        tags.get("addr:postcode"),
    ]
    return ", ".join(part for part in parts if part)


def _point(geometry: dict) -> tuple[float, float] | None:
    """A single lat/lon for a feature, whatever shape it is.

    A pharmacy is usually a node and sometimes a building outline. For an
    outline the centroid of its first ring is close enough — the error is the
    width of a shop, and the distance shown to a family is rounded to the
    nearest hundred metres and called a rough guide.
    """
    kind = (geometry or {}).get("type")
    coords = (geometry or {}).get("coordinates")
    if not coords:
        return None
    if kind == "Point":
        longitude, latitude = coords[0], coords[1]
        return float(latitude), float(longitude)
    if kind in {"Polygon", "MultiPolygon"}:
        ring = coords[0][0] if kind == "MultiPolygon" else coords[0]
        if not ring:
            return None
        longitude = sum(p[0] for p in ring) / len(ring)
        latitude = sum(p[1] for p in ring) / len(ring)
        return float(latitude), float(longitude)
    return None


def features(path: Path) -> Iterator[dict]:
    """Each feature in the file, whether it is GeoJSON or line-delimited.

    `osmium export` writes one JSON object per line by default and a single
    FeatureCollection with `-f geojson`. Both are common enough that guessing
    wrong wastes a 100 MB download, so both are read.
    """
    text = path.read_text()
    stripped = text.lstrip()
    if stripped.startswith("{") and '"FeatureCollection"' in stripped[:200]:
        yield from json.loads(text).get("features", [])
        return
    for line in text.splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)


def rows_from(path: Path, *, now: datetime) -> list[dict]:
    """Every feature in the file that is a place we show, as table rows."""
    rows: dict[str, dict] = {}
    skipped = 0
    for feature in features(path):
        tags = feature.get("properties") or {}
        kind = kind_of(tags)
        if kind is None:
            skipped += 1
            continue
        point = _point(feature.get("geometry") or {})
        if point is None:
            skipped += 1
            continue
        osm_id = str(feature.get("id") or tags.get("@id") or "").strip()
        if not osm_id:
            skipped += 1
            continue
        latitude, longitude = point
        # Last one wins, which matters when a file contains both a node and
        # the building around it for the same shop.
        rows[osm_id] = place_row(
            osm_id=osm_id,
            kind=kind,
            name=tags.get("name") or "",
            address=address_of(tags),
            latitude=latitude,
            longitude=longitude,
            phone=tags.get("phone") or tags.get("contact:phone"),
            opening_hours=tags.get("opening_hours"),
            loaded_at=now,
        )
    logger.info("read %d places, skipped %d features", len(rows), skipped)
    return list(rows.values())


def _sessions():
    """The records database, where migration 0015 makes the table.

    Not `db.session.get_sessionmaker()`: that is the *app* database. They are
    two different SQLite files, and loading into the wrong one produces a
    table that is full and a screen that is empty, with nothing to say why.
    """
    url = get_settings().records_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    return sessionmaker(engine, expire_on_commit=False), url


def write(rows: list[dict]) -> int:
    """Upsert every row. Returns how many were written."""
    sessions, url = _sessions()
    maker = pg_insert if url.startswith("postgres") else sqlite_insert

    written = 0
    with sessions.begin() as session:
        # In batches: a single statement with eighty thousand rows in it is
        # refused by some drivers and unreadable in a log when it fails.
        for start in range(0, len(rows), 500):
            batch = rows[start : start + 500]
            statement = maker(PlaceRow).values(batch)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[PlaceRow.id],
                    set_={
                        column: statement.excluded[column]
                        for column in (
                            "kind", "name", "address", "latitude",
                            "longitude", "phone", "opening_hours", "loaded_at",
                        )
                    },
                )
            )
            written += len(batch)
    return written


def count() -> int:
    sessions, _ = _sessions()
    with sessions() as session:
        return int(session.execute(select(func.count(PlaceRow.id))).scalar() or 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="GeoJSON from `osmium export`")
    parser.add_argument("--write", action="store_true", help="actually load it")
    args = parser.parse_args(argv)

    if not args.file.exists():
        print(f"  no such file: {args.file}")
        return 1

    rows = rows_from(args.file, now=datetime.now(UTC))
    if not rows:
        print("  nothing in that file is a place we show. Check the osmium filter.")
        return 1

    by_kind: dict[str, int] = {}
    for row in rows:
        by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1
    print(f"  {len(rows)} places:")
    for kind, how_many in sorted(by_kind.items(), key=lambda pair: -pair[1]):
        print(f"    {kind:16} {how_many}")

    if not args.write:
        print("\n  Nothing was written. Pass --write to load it.")
        return 0

    before = count()
    written = write(rows)
    after = count()
    print(f"\n  wrote {written} rows; the table went from {before} to {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
