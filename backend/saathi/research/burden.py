"""What EKYATRA can contribute to cancer research, and what it must not.

India has cancer registries. It has treatment outcomes, staging, survival.
What it has almost none of is the thing that decides whether a patient
finishes treatment at all: **how far they had to come, what it cost them, how
many journeys were wasted, and how long they waited.** Clinicians say
"loss to follow-up" and the reason is usually a bus fare and a working day,
and almost nobody has the numbers.

That is exactly what this system holds, as a side effect of doing its job. So
it is worth contributing — and it is safe to contribute, because of what this
system deliberately never collected.

**What leaves, in one sentence:** travel and cost burden, with no clinical
value in it, because there is no clinical value in this system to leak.

WHAT IS INCLUDED

  distance band, journey hours band, trips made, trips wasted, nights away,
  the cost the family themselves stated, days a step was delayed, the
  clinic's own running-late figure, the care pathway's name, the month.

WHAT IS REMOVED, AND WHY EACH ONE

  name, phone, email         direct identifiers
  ABHA number                a national identifier; re-identifies instantly
  patient id                 ours, but a stable key across exports lets two
                             releases be joined back into a person
  exact dates                a date of travel plus a district is close to
                             unique; the month is not
  exact distance             "1,020 km from Gaya to Mumbai" names one
                             hospital pair and nearly one patient. Banded.
  district                   kept only as a state. A district plus a rare
                             pathway is identifying in a way a state is not.
  free text                  anything a family typed, including the sentence
                             a cost was quoted in. It is evidence to a
                             navigator and a re-identification risk here.

**Consent is per-patient and never assumed.** `ConsentPurpose.RESEARCH`
already exists in this codebase and its docstring already says the right
thing: *optional, and never a condition of care*. A family with no active
research grant contributes no row. Not an anonymised row — no row. The export
reports how many were excluded for that reason, because a dataset that does
not say what it is missing invites the reader to assume it is complete.

**No clinical data is brokered.** This does not reach into the hospital and
fetch records on a researcher's behalf. It contributes what EKYATRA itself
observed. A system that offered to be a consent gateway for clinical records
would be a different and much larger claim, and not one this architecture
has earned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum

#: The receiving body. Named rather than generic because an export addressed
#: to nobody is a file, not a contribution — and because the National Cancer
#: Grid is the real destination for this kind of data in India: 300+ centres,
#: coordinated from Tata Memorial, already pooling treatment data.
RECIPIENT = "National Cancer Grid (NCG), India"

#: Bumped whenever a column is added, removed or redefined. A researcher
#: joining two releases needs to know the columns mean the same thing.
SCHEMA_VERSION = "burden-1.0"


class DistanceBand(StrEnum):
    """Distance, coarse enough not to name a hospital pair.

    "1,020 km from Gaya" identifies one route and very nearly one patient.
    The bands are set where travel actually changes character: a day trip, an
    overnight, a two-day journey.
    """

    UNDER_50 = "under_50km"
    KM_50_150 = "50_150km"
    KM_150_400 = "150_400km"
    KM_400_800 = "400_800km"
    OVER_800 = "over_800km"

    @classmethod
    def of(cls, km: float) -> DistanceBand:
        if km < 50:
            return cls.UNDER_50
        if km < 150:
            return cls.KM_50_150
        if km < 400:
            return cls.KM_150_400
        if km < 800:
            return cls.KM_400_800
        return cls.OVER_800


#: Districts map to states. A district plus an uncommon pathway can identify
#: somebody; a state cannot. This is the only geography that leaves.
_STATE_OF: dict[str, str] = {
    "Gaya": "Bihar",
    "Darbhanga": "Bihar",
    "Samastipur": "Bihar",
    "Patna": "Bihar",
    "Muzaffarpur": "Bihar",
    "Mirzapur": "Uttar Pradesh",
    "Varanasi": "Uttar Pradesh",
    "Bardhaman": "West Bengal",
    "Kolkata": "West Bengal",
    "Mumbai": "Maharashtra",
}


def state_of(district: str) -> str:
    """The state a district sits in, or "unknown".

    "unknown" rather than the district itself. Falling back to the district
    would mean an unmapped one silently becomes the most identifying column
    in the file — the failure would be invisible and in the wrong direction.
    """
    return _STATE_OF.get((district or "").strip(), "unknown")


@dataclass(frozen=True)
class BurdenRow:
    """One family's journey burden, as it leaves this system.

    Every field here survived the question "could this, with the others,
    name somebody?". There is deliberately no patient key of any kind: not a
    hash, not a pseudonym. A stable pseudonym across two releases lets them
    be joined, and a joined pair is far more identifying than either.
    """

    #: Which release this row belongs to. Not a patient key.
    release: str
    state: str
    distance_band: DistanceBand
    #: Round-trip hours, to the nearest whole hour.
    journey_hours: int | None
    #: The care pathway's name — "oncology", "dialysis". Not a diagnosis.
    pathway: str
    #: YYYY-MM. Never a day.
    month: str
    trips_made: int
    #: Journeys where the family travelled and the step could not happen.
    #: The number this whole export exists for.
    trips_wasted: int
    nights_away: int
    #: What the family themselves said a journey costs, in rupees. None when
    #: they never said — never an estimate.
    stated_cost_inr: int | None
    #: Days the care step moved from its first booked date.
    days_delayed: int | None
    #: The clinic's own running-late figure on the day they attended.
    clinic_late_minutes: int | None

    def as_csv_row(self) -> list[str]:
        def text(value: object) -> str:
            return "" if value is None else str(value)

        return [
            self.release, self.state, self.distance_band.value,
            text(self.journey_hours), self.pathway, self.month,
            text(self.trips_made), text(self.trips_wasted), text(self.nights_away),
            text(self.stated_cost_inr), text(self.days_delayed),
            text(self.clinic_late_minutes),
        ]


COLUMNS = [
    "release", "state", "distance_band", "journey_hours", "pathway", "month",
    "trips_made", "trips_wasted", "nights_away", "stated_cost_inr",
    "days_delayed", "clinic_late_minutes",
]

#: Stated in the manifest so a reader does not have to infer it from absence.
REMOVED = [
    ("name, phone, email", "direct identifiers"),
    ("ABHA number", "a national identifier; re-identifies instantly"),
    ("patient id", "a stable key across releases lets two be joined back to a person"),
    ("exact dates", "a travel date plus a place is close to unique; the month is not"),
    ("exact distance", "names one hospital pair, and nearly one patient"),
    ("district", "kept only as a state; a district plus a rare pathway identifies"),
    ("free text", "a family's own words are evidence to a navigator and a risk here"),
    ("anything clinical", "this system never collected a result, a stage or a diagnosis"),
]


@dataclass
class Release:
    """A dataset, and an honest account of what is and is not in it."""

    release: str
    recipient: str = RECIPIENT
    schema_version: str = SCHEMA_VERSION
    prepared_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    rows: list[BurdenRow] = field(default_factory=list)
    #: Families who had no active research grant. Counted, never included.
    without_consent: int = 0
    #: Families whose records were too thin to say anything useful.
    too_little_data: int = 0

    @property
    def families(self) -> int:
        return len(self.rows)

    def manifest(self) -> dict:
        """What a recipient needs in order to trust and interpret the file.

        The counts of what was *left out* matter as much as the data. A file
        of 2 rows from a cohort of 50 is a different claim from 2 rows out of
        2, and a reader who cannot tell will assume the flattering one.
        """
        considered = self.families + self.without_consent + self.too_little_data
        return {
            "release": self.release,
            "recipient": self.recipient,
            "schema_version": self.schema_version,
            "prepared_at": self.prepared_at.isoformat(),
            "rows": self.families,
            "families_considered": considered,
            "excluded_no_research_consent": self.without_consent,
            "excluded_too_little_data": self.too_little_data,
            "consent_basis": (
                "ConsentPurpose.RESEARCH, granted per patient, revocable, and "
                "never a condition of care. A family without an active grant "
                "contributes no row at all."
            ),
            "columns": COLUMNS,
            "removed_before_export": [
                {"field": field_name, "why": why} for field_name, why in REMOVED
            ],
            "contains_clinical_data": False,
            "re_identification_note": (
                "No patient key of any kind is included, not even a salted "
                "hash: a stable pseudonym would let two releases be joined, "
                "and a joined pair identifies far more than either alone."
            ),
        }

    def to_csv(self) -> str:
        lines = [",".join(COLUMNS)]
        lines.extend(",".join(row.as_csv_row()) for row in self.rows)
        return "\n".join(lines) + "\n"


def month_of(when: date | datetime | None) -> str:
    if when is None:
        return ""
    return f"{when.year:04d}-{when.month:02d}"


__all__ = [
    "COLUMNS",
    "RECIPIENT",
    "REMOVED",
    "SCHEMA_VERSION",
    "BurdenRow",
    "DistanceBand",
    "Release",
    "month_of",
    "state_of",
]
