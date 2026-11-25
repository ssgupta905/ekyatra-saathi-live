"""Healthcare places read from our own table instead of a public server.

The live Overpass readers answer in thirty to forty seconds when they answer
at all, so the same data is loaded monthly and queried locally. That swap is
only safe if the local copy behaves like the live one, and these tests pin
the four ways it could quietly not:

* a bounding box that finds the right places but also ones beyond the radius,
  because longitude degrees are narrower in India than at the equator;
* a loader that inserts instead of upserting, doubling the table every month;
* two definitions of "pharmacy" — one in the Overpass selectors, one in the
  loader's tag filter — that drift apart and send a family to the wrong shop;
* a rating creeping in, which nothing in this project may order a clinic by.

The tags in `FEATURES` are the shapes `osmium export` actually emits: a node
with a point, a building with a polygon, a Jan Aushadhi store that is also
tagged `amenity=pharmacy`, and entries with no name or no hours.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from saathi.adapters.places.sql import SqlPlaces, metres_between, place_row
from saathi.db.tables import Base, PlaceRow
from saathi.domain.places import PlaceKind
from saathi.tools.load_places import address_of, kind_of, rows_from
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

#: Tata Memorial Hospital, Parel. Everything below is placed relative to it.
HOSPITAL = (19.0043, 72.8428)

NOW = datetime(2026, 11, 25, tzinfo=UTC)


def _row(osm_id, kind, name, lat, lon, *, hours=None, phone=None, address=""):
    return place_row(
        osm_id=osm_id, kind=kind, name=name, address=address,
        latitude=lat, longitude=lon, phone=phone,
        opening_hours=hours, loaded_at=NOW,
    )


@pytest_asyncio.fixture
async def places(tmp_path):
    """A real database on disk, with the real table.

    A file rather than `:memory:`, because the adapter opens its own engine
    from a URL — the way every records adapter here does — and two engines
    cannot share one in-memory SQLite database.
    """
    url = f"sqlite:///{tmp_path / 'records.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    finder = SqlPlaces(url)
    yield sessions, finder
    await finder.close()
    engine.dispose()


async def _load(sessions, rows):
    with sessions.begin() as session:
        for row in rows:
            session.add(PlaceRow(**row))


class TestFindingWhatIsNear:
    async def test_the_nearest_comes_first(self, places) -> None:
        sessions, finder = places
        await _load(sessions, [
            _row("node/3", PlaceKind.PHARMACY, "Far", 19.0160, 72.8428),      # ~1.3 km
            _row("node/1", PlaceKind.PHARMACY, "Next door", 19.0045, 72.8428),  # ~22 m
            _row("node/2", PlaceKind.PHARMACY, "Down the road", 19.0070, 72.8428),  # ~300 m
        ])

        found = await finder.nearby(PlaceKind.PHARMACY, *HOSPITAL, radius_m=3000)

        assert [p.name for p in found] == ["Next door", "Down the road", "Far"]

    async def test_another_kind_is_not_returned(self, places) -> None:
        sessions, finder = places
        await _load(sessions, [
            _row("node/1", PlaceKind.PHARMACY, "Chemist", 19.0045, 72.8428),
            _row("node/2", PlaceKind.LAB, "Pathology", 19.0046, 72.8428),
        ])

        found = await finder.nearby(PlaceKind.LAB, *HOSPITAL, radius_m=3000)

        assert [p.name for p in found] == ["Pathology"]

    async def test_outside_the_radius_is_excluded(self, places) -> None:
        sessions, finder = places
        await _load(sessions, [
            _row("node/1", PlaceKind.PHARMACY, "Inside", 19.0070, 72.8428),   # ~300 m
            _row("node/2", PlaceKind.PHARMACY, "Outside", 19.0400, 72.8428),  # ~4 km
        ])

        found = await finder.nearby(PlaceKind.PHARMACY, *HOSPITAL, radius_m=1000)

        assert [p.name for p in found] == ["Inside"]

    async def test_the_box_corner_is_trimmed_to_a_circle(self, places) -> None:
        """A box around a 1 km radius reaches 1.41 km at its corners.

        Without the distance check after the query, a place diagonally beyond
        the radius comes back as "within 1 km" — which is how a family is sent
        forty per cent further than they were told.
        """
        sessions, finder = places
        # Due north-east of the hospital, ~0.9 km on each axis: inside the
        # bounding box, about 1.27 km away, outside a 1 km circle.
        corner = (HOSPITAL[0] + 0.0081, HOSPITAL[1] + 0.0086)
        await _load(sessions, [_row("node/1", PlaceKind.PHARMACY, "Corner", *corner)])

        assert metres_between(*HOSPITAL, *corner) > 1000
        assert await finder.nearby(PlaceKind.PHARMACY, *HOSPITAL, radius_m=1000) == []
        assert len(await finder.nearby(PlaceKind.PHARMACY, *HOSPITAL, radius_m=2000)) == 1

    async def test_longitude_is_scaled_for_latitude(self, places) -> None:
        """A degree of longitude is ~5% shorter at Mumbai than at the equator.

        A box that forgot the cosine would be too narrow east-west and would
        silently miss places at the edge of the radius.
        """
        sessions, finder = places
        # 2.9 km due east, inside a 3 km radius — but only just, which is the
        # point. A box that forgot the cosine is 5% narrower east-west, and
        # 2.9 km falls outside it while still being inside the circle. Put
        # the place at 2.5 km and the test passes either way and proves
        # nothing.
        east = (HOSPITAL[0], HOSPITAL[1] + 2900 / (111_320 * 0.9455))
        await _load(sessions, [_row("node/1", PlaceKind.PHARMACY, "East", *east)])

        assert metres_between(*HOSPITAL, *east) < 3000
        found = await finder.nearby(PlaceKind.PHARMACY, *HOSPITAL, radius_m=3000)

        assert [p.name for p in found] == ["East"]

    async def test_an_empty_table_is_an_empty_answer_not_an_error(self, places) -> None:
        _sessions, finder = places
        assert await finder.nearby(PlaceKind.PHARMACY, *HOSPITAL) == []


class TestWhatAPlaceSays:
    async def test_hours_are_parsed_by_the_same_parser_as_the_live_reader(
        self, places
    ) -> None:
        """Two parsers for one format drift, and the day they disagree a
        family is told a shop is open when it is closed."""
        sessions, finder = places
        await _load(sessions, [
            _row("node/1", PlaceKind.PHARMACY, "Chemist", 19.0045, 72.8428,
                 hours="Mo-Sa 09:00-21:00"),
        ])

        (place,) = await finder.nearby(PlaceKind.PHARMACY, *HOSPITAL)

        assert place.periods, "the stored opening_hours string was not parsed"
        # Monday lunchtime open, Sunday lunchtime closed.
        assert place.open_at(datetime(2026, 11, 23, 13, 0, tzinfo=UTC)) is True
        assert place.open_at(datetime(2026, 11, 22, 13, 0, tzinfo=UTC)) is False

    async def test_open_now_is_never_asserted_from_a_month_old_table(
        self, places
    ) -> None:
        """`open_now` means "open at the instant the service was asked".

        This table was written weeks ago. Answering it would be a claim about
        right now built from something that was true in October.
        """
        sessions, finder = places
        await _load(sessions, [
            _row("node/1", PlaceKind.PHARMACY, "Chemist", 19.0045, 72.8428,
                 hours="24/7"),
        ])

        (place,) = await finder.nearby(PlaceKind.PHARMACY, *HOSPITAL)

        assert place.open_now is None

    async def test_the_source_says_where_it_came_from(self, places) -> None:
        sessions, finder = places
        await _load(sessions, [_row("node/1", PlaceKind.PHARMACY, "C", 19.0045, 72.8428)])

        (place,) = await finder.nearby(PlaceKind.PHARMACY, *HOSPITAL)

        assert place.source == "osm-local"
        assert place.maps_uri and "openstreetmap.org" in place.maps_uri


class TestTheLoader:
    def test_a_jan_aushadhi_store_is_not_filed_as_an_ordinary_pharmacy(self) -> None:
        """They are also `amenity=pharmacy`, and they are the better answer.

        Government generic-medicine shops are cheaper, which is why
        `KINDS_FOR_NEED` offers them first when money is tight. Checking
        pharmacy first would hide every one of them.
        """
        assert kind_of({"amenity": "pharmacy", "name": "Jan Aushadhi Kendra"}) is (
            PlaceKind.JAN_AUSHADHI
        )
        assert kind_of({"amenity": "pharmacy", "brand": "Jan  Aushadhi"}) is (
            PlaceKind.JAN_AUSHADHI
        )
        assert kind_of({"amenity": "pharmacy", "name": "City Chemist"}) is PlaceKind.PHARMACY

    @pytest.mark.parametrize(
        ("tags", "expected"),
        [
            ({"healthcare": "laboratory"}, PlaceKind.LAB),
            ({"amenity": "doctors", "name": "Suburban Diagnostics"}, PlaceKind.LAB),
            ({"healthcare": "physiotherapist"}, PlaceKind.PHYSIO),
            ({"shop": "medical_supply"}, PlaceKind.EQUIPMENT),
            ({"amenity": "clinic", "name": "Shah Clinic"}, PlaceKind.CLINIC),
            ({"amenity": "restaurant"}, None),
            ({}, None),
        ],
    )
    def test_tags_map_to_the_kinds_the_overpass_selectors_use(self, tags, expected) -> None:
        assert kind_of(tags) is expected

    def test_every_kind_the_app_asks_for_can_be_loaded(self) -> None:
        """A kind the screen offers and the loader cannot produce is a tab
        that is always empty, with nothing to say why."""
        from saathi.adapters.places.osm import _SELECT

        loadable = {
            kind_of(tags)
            for tags in (
                {"amenity": "pharmacy"},
                {"amenity": "pharmacy", "name": "Jan Aushadhi"},
                {"healthcare": "laboratory"},
                {"shop": "medical_supply"},
                {"amenity": "clinic"},
                {"healthcare": "physiotherapist"},
            )
        }
        assert set(_SELECT) <= loadable, (
            f"the live reader finds kinds the loader cannot: {set(_SELECT) - loadable}"
        )

    def test_an_address_reads_the_way_an_indian_address_is_written(self) -> None:
        assert address_of({
            "addr:housenumber": "12", "addr:street": "Dr E Borges Rd",
            "addr:suburb": "Parel", "addr:city": "Mumbai", "addr:postcode": "400012",
        }) == "12, Dr E Borges Rd, Parel, Mumbai, 400012"
        assert address_of({}) == ""

    def test_a_building_outline_becomes_one_point(self, tmp_path: Path) -> None:
        """Pharmacies are usually nodes and sometimes building polygons.

        The centroid is wrong by the width of a shop, and the distance shown
        is rounded to the nearest hundred metres and called a rough guide.
        """
        path = tmp_path / "places.geojson"
        path.write_text(json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "id": "way/42",
                "properties": {"amenity": "pharmacy", "name": "Corner Chemist"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[72.84, 19.00], [72.85, 19.00],
                                     [72.85, 19.01], [72.84, 19.01]]],
                },
            }],
        }))

        (row,) = rows_from(path, now=NOW)

        assert row["id"] == "way/42"
        assert row["latitude"] == pytest.approx(19.005, abs=0.001)
        assert row["longitude"] == pytest.approx(72.845, abs=0.001)

    def test_line_delimited_json_is_read_too(self, tmp_path: Path) -> None:
        """`osmium export` writes one object per line unless told otherwise,
        and guessing wrong wastes a 100 MB download."""
        path = tmp_path / "places.ldjson"
        path.write_text("\n".join(json.dumps(feature) for feature in [
            {"type": "Feature", "id": "node/1",
             "properties": {"amenity": "pharmacy", "name": "One"},
             "geometry": {"type": "Point", "coordinates": [72.8428, 19.0045]}},
            {"type": "Feature", "id": "node/2",
             "properties": {"amenity": "restaurant"},
             "geometry": {"type": "Point", "coordinates": [72.8428, 19.0045]}},
        ]))

        rows = rows_from(path, now=NOW)

        assert [row["id"] for row in rows] == ["node/1"]

    def test_the_same_place_twice_in_one_file_is_one_row(self, tmp_path: Path) -> None:
        """A file often holds both a node and the building around it."""
        path = tmp_path / "p.ldjson"
        same = {"type": "Feature", "id": "node/7",
                "properties": {"amenity": "pharmacy", "name": "Chemist"},
                "geometry": {"type": "Point", "coordinates": [72.8428, 19.0045]}}
        path.write_text(json.dumps(same) + "\n" + json.dumps(same))

        assert len(rows_from(path, now=NOW)) == 1

    def test_a_feature_with_no_geometry_is_skipped_not_guessed(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "p.ldjson"
        path.write_text(json.dumps({
            "type": "Feature", "id": "node/9",
            "properties": {"amenity": "pharmacy", "name": "Nowhere"},
            "geometry": {},
        }))

        assert rows_from(path, now=NOW) == []


class TestNoRatingsEver:
    """Nothing in this project orders a clinic by what strangers thought.

    A column that existed would eventually be filled, so the check is
    structural rather than behavioural.
    """

    def test_the_table_has_no_rating_column(self) -> None:
        columns = {column.name for column in PlaceRow.__table__.columns}
        for forbidden in ("rating", "reviews", "review_count", "stars", "score"):
            assert forbidden not in columns

    def test_the_loader_never_reads_one(self) -> None:
        source = Path("backend/saathi/tools/load_places.py").read_text().lower()
        for forbidden in ("rating", "review", "stars"):
            # The word appears in prose explaining why it is absent; what must
            # not appear is a tag lookup for it.
            assert f'"{forbidden}"' not in source
            assert f"'{forbidden}'" not in source
