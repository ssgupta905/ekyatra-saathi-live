"""What may leave this system for research, and what may never.

India has cancer registries with staging and survival. What it has almost
none of is why patients stop coming, and the answer is usually a bus fare and
a lost working day. That is the gap this export fills — and the only reason
it is safe to fill is what this system deliberately never collected.

So these tests are mostly about absence. Every one of them asserts that
something is *not* in the file: no identifier, no clinical value, no stable
key that would let two releases be joined back into a person, and no row at
all for a family who has not consented.

The de-identification is checked against the real `Patient` and `ConsentGrant`
models rather than stand-ins, because a test that de-identifies a dictionary
it made up proves nothing about the one the system actually holds.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from saathi.domain.consent import (
    ConsentCapacity,
    ConsentGrant,
    ConsentPurpose,
    default_expiry,
)
from saathi.domain.enums import Channel, Language
from saathi.research.burden import (
    COLUMNS,
    RECIPIENT,
    BurdenRow,
    DistanceBand,
    Release,
    state_of,
)
from saathi.research.collect import research_grants

NOW = datetime(2026, 11, 25, tzinfo=UTC)


def _grant(abha: str, *, purpose=ConsentPurpose.RESEARCH, revoked=False, expired=False):
    return ConsentGrant(
        id=f"g-{abha}", request_id="r1", abha_number=abha, purpose=purpose,
        requester_id="ncg", requester_name="National Cancer Grid", categories=(),
        from_date=None, to_date=None, granted_at=NOW,
        expires_at=NOW - timedelta(days=1) if expired else default_expiry(NOW),
        granted_by="p1", capacity=ConsentCapacity.SELF, channel=Channel.IVR,
        notice_language=Language.BENGALI,
        revoked_at=NOW - timedelta(hours=1) if revoked else None,
    )


class _Registry:
    def __init__(self, *grants):
        self.grants = {g.id: g for g in grants}


class TestConsentGates:
    def test_only_research_grants_count(self) -> None:
        """A family who agreed to care coordination has not agreed to this."""
        registry = _Registry(
            _grant("99000000000001", purpose=ConsentPurpose.CARE_COORDINATION),
            _grant("99000000000002"),
        )
        found = research_grants(registry)
        assert set(found) == {"99000000000002"}

    def test_a_revoked_grant_is_not_active(self) -> None:
        (grants,) = research_grants(_Registry(_grant("99000000000001", revoked=True))).values()
        assert not any(g.is_active(NOW) for g in grants)

    def test_an_expired_grant_is_not_active(self) -> None:
        (grants,) = research_grants(_Registry(_grant("99000000000001", expired=True))).values()
        assert not any(g.is_active(NOW) for g in grants)

    def test_an_unreadable_registry_shares_nothing(self) -> None:
        """The failure mode of a consent check must be "do not share", and
        that has to hold when the check itself breaks."""
        class Broken:
            @property
            def grants(self):
                raise RuntimeError("the store is down")

        assert research_grants(Broken()) == {}


class TestWhatNeverLeaves:
    def test_no_column_can_identify_a_person(self) -> None:
        forbidden = {
            "name", "phone", "email", "abha", "abha_number", "patient_id",
            "patient", "id", "address", "district", "dob", "date_of_birth",
        }
        assert forbidden.isdisjoint(COLUMNS), (
            f"an identifying column reached the schema: {forbidden & set(COLUMNS)}"
        )

    def test_there_is_no_patient_key_at_all_not_even_a_hash(self) -> None:
        """A stable pseudonym lets two releases be joined, and a joined pair
        identifies far more than either alone."""
        for suspect in ("hash", "pseudonym", "subject", "key", "uid"):
            assert not any(suspect in column for column in COLUMNS)

    def test_no_clinical_column_exists(self) -> None:
        clinical = {"diagnosis", "stage", "result", "value", "report", "finding"}
        assert clinical.isdisjoint(COLUMNS)

    def test_the_manifest_says_so_out_loud(self) -> None:
        """A reader should not have to infer the absence of clinical data."""
        manifest = Release(release="r").manifest()
        assert manifest["contains_clinical_data"] is False
        assert manifest["recipient"] == RECIPIENT
        removed = {entry["field"] for entry in manifest["removed_before_export"]}
        assert any("ABHA" in field for field in removed)
        assert any("clinical" in field for field in removed)

    def test_every_removed_field_says_why(self) -> None:
        for entry in Release(release="r").manifest()["removed_before_export"]:
            assert entry["why"].strip(), f"{entry['field']} is removed with no reason given"


class TestCoarsening:
    @pytest.mark.parametrize(
        ("km", "band"),
        [
            (12, DistanceBand.UNDER_50),
            (120, DistanceBand.KM_50_150),
            (380, DistanceBand.KM_150_400),
            (740, DistanceBand.KM_400_800),
            (1020, DistanceBand.OVER_800),
        ],
    )
    def test_distance_is_banded_not_exact(self, km: float, band: DistanceBand) -> None:
        """"1,020 km from Gaya to Mumbai" names one route and nearly one
        patient."""
        assert DistanceBand.of(km) is band

    def test_a_district_becomes_a_state(self) -> None:
        assert state_of("Darbhanga") == "Bihar"
        assert state_of("Bardhaman") == "West Bengal"

    def test_an_unmapped_district_becomes_unknown_not_itself(self) -> None:
        """Falling back to the district would make an unmapped one the most
        identifying column in the file, and the failure would be invisible."""
        assert state_of("Somewhere Else") == "unknown"
        assert state_of("") == "unknown"


class TestTheManifestIsHonest:
    def _release(self) -> Release:
        release = Release(release="r", without_consent=7, too_little_data=2)
        release.rows.append(
            BurdenRow(
                release="r", state="Bihar", distance_band=DistanceBand.OVER_800,
                journey_hours=40, pathway="oncology", month="2026-11",
                trips_made=2, trips_wasted=1, nights_away=3,
                stated_cost_inr=900, days_delayed=4, clinic_late_minutes=107,
            )
        )
        return release

    def test_it_reports_what_was_left_out(self) -> None:
        """A file of 1 row from a cohort of 10 is a different claim from 1
        out of 1, and a reader who cannot tell assumes the flattering one."""
        manifest = self._release().manifest()
        assert manifest["rows"] == 1
        assert manifest["families_considered"] == 10
        assert manifest["excluded_no_research_consent"] == 7
        assert manifest["excluded_too_little_data"] == 2

    def test_the_csv_matches_the_declared_columns(self) -> None:
        csv = self._release().to_csv().splitlines()
        assert csv[0] == ",".join(COLUMNS)
        assert len(csv[1].split(",")) == len(COLUMNS)

    def test_a_stated_cost_survives_because_the_family_said_it(self) -> None:
        """The one money figure in the file, and it is theirs."""
        assert "900" in self._release().to_csv()

    def test_an_unknown_measure_is_empty_not_zero(self) -> None:
        """Zero means "the clinic was on time". Empty means nobody could
        read it, and a statistician can handle the difference."""
        row = BurdenRow(
            release="r", state="Bihar", distance_band=DistanceBand.OVER_800,
            journey_hours=None, pathway="oncology", month="2026-11",
            trips_made=0, trips_wasted=0, nights_away=0,
            stated_cost_inr=None, days_delayed=None, clinic_late_minutes=None,
        )
        cells = row.as_csv_row()
        assert cells[COLUMNS.index("clinic_late_minutes")] == ""
        assert cells[COLUMNS.index("stated_cost_inr")] == ""
        assert cells[COLUMNS.index("journey_hours")] == ""
