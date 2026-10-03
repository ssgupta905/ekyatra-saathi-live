"""The two demo families from the team brief, seeded onto real steps.

`seed_shambhu_prasad` and `seed_anita_devi` do not touch the 50-family
cohort `generate.py` produces — `build_scripted_cohort` appends them to it,
so the existing demo (`make demo`, the default live world) is unaffected.
Dates, resource names and numbers echo the brief closely enough to narrate
on stage; they are still synthetic, same as the rest of this module's cohort.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..domain.enums import DisruptionKind, Language, Role, StepKind, StepStatus
from ..domain.models import CareStep, MaintenanceCycle, Patient
from .generate import GroundTruth, SyntheticCohort, generate_cohort

SHAMBHU_ID = "P-SHAMBHU"
ANITA_ID = "P-ANITA"

#: Resource ids the scripted disruptions are raised against. Registered on
#: the world so a desk can report them by name, the same as a real one would.
MRI_2 = "MRI-2"
PET_CT_SCANNER = "PET-CT"
ECHO_CARDIOLOGIST = "echo-cardiologist"
DAY_CARE_PHARMACY = "day-care-pharmacy"


def seed_shambhu_prasad(today: date) -> tuple[Patient, tuple[CareStep, ...], GroundTruth]:
    """Story 1: referral through the scan chain, MRI-2 due to fail on `today`."""
    first_visit = today - timedelta(days=2)
    scan_day = today  # the morning the MRI machine fails
    patient = Patient(
        id=SHAMBHU_ID,
        home_distance_km=1771.0,
        home_district="Gaya",
        language=Language.HINDI,
        caregiver_phone="+919800000001",
        hospital_id="TMH-MUM",
    )
    steps = (
        CareStep(id=f"{SHAMBHU_ID}-consult", patient_id=SHAMBHU_ID, kind=StepKind.CONSULT,
                 status=StepStatus.COMPLETED, scheduled_for=first_visit,
                 completed_on=first_visit, queue="consult"),
        CareStep(id=f"{SHAMBHU_ID}-biopsy", patient_id=SHAMBHU_ID, kind=StepKind.BIOPSY,
                 status=StepStatus.COMPLETED, scheduled_for=first_visit,
                 completed_on=first_visit, queue="biopsy"),
        CareStep(id=f"{SHAMBHU_ID}-bloods", patient_id=SHAMBHU_ID, kind=StepKind.BLOODS,
                 status=StepStatus.COMPLETED, scheduled_for=first_visit,
                 completed_on=first_visit, queue="bloods"),
        # The MRI, on the machine that fails this morning.
        CareStep(id=f"{SHAMBHU_ID}-scan", patient_id=SHAMBHU_ID, kind=StepKind.SCAN,
                 status=StepStatus.SCHEDULED, scheduled_for=scan_day,
                 queue="radiology", resource_id=MRI_2),
        CareStep(id=f"{SHAMBHU_ID}-pathology_report", patient_id=SHAMBHU_ID,
                 kind=StepKind.PATHOLOGY_REPORT, status=StepStatus.RESULT_AVAILABLE,
                 completed_on=first_visit, result_available_on=first_visit + timedelta(days=1),
                 queue="pathology_report"),
        CareStep(id=f"{SHAMBHU_ID}-radiology_report", patient_id=SHAMBHU_ID,
                 kind=StepKind.RADIOLOGY_REPORT, status=StepStatus.PENDING_RESULT,
                 completed_on=scan_day, queue="radiology_report"),
        CareStep(id=f"{SHAMBHU_ID}-review", patient_id=SHAMBHU_ID, kind=StepKind.REVIEW_CONSULT,
                 status=StepStatus.SCHEDULED, scheduled_for=scan_day + timedelta(days=1),
                 queue="review_consult"),
        # Booked four days after the MRI: the gap `care_rules.STEP_LEAD_DAYS`
        # keeps between a scan and the functional scan that follows it.
        CareStep(id=f"{SHAMBHU_ID}-pet_ct", patient_id=SHAMBHU_ID, kind=StepKind.PET_CT,
                 status=StepStatus.SCHEDULED, scheduled_for=scan_day + timedelta(days=4),
                 queue="pet_ct", resource_id=PET_CT_SCANNER),
        # The consultants' meeting the whole stay is anchored to. It sits on a
        # standing Tue/Fri slot, which is why a two-day scan slip can cost four
        # nights — the next meeting is not the next day.
        CareStep(id=f"{SHAMBHU_ID}-joint_clinic", patient_id=SHAMBHU_ID,
                 kind=StepKind.JOINT_CLINIC, status=StepStatus.SCHEDULED,
                 scheduled_for=scan_day + timedelta(days=8), queue="joint_clinic"),
    )
    truth = GroundTruth(
        patient_id=SHAMBHU_ID,
        true_ready_on={f"{SHAMBHU_ID}-radiology_report": scan_day + timedelta(days=1)},
        naive_return_date=scan_day + timedelta(days=8),
        naive_target_step_id=f"{SHAMBHU_ID}-joint_clinic",
    )
    return patient, steps, truth


def seed_anita_devi(
    today: date,
) -> tuple[Patient, tuple[CareStep, ...], GroundTruth, MaintenanceCycle]:
    """Story 2: maintenance, sitting at dose 13 — echo-gated — the day the
    hub's only echo cardiologist goes on emergency leave."""
    long_ago = today - timedelta(days=250)
    echo_day = today
    dose_day = today + timedelta(days=2)
    patient = Patient(
        id=ANITA_ID,
        home_distance_km=90.0,
        home_district="Samastipur",
        language=Language.HINDI,
        caregiver_phone="+919800000002",
        hospital_id="HBCH-MZP",
    )
    history_kinds = (
        StepKind.CONSULT, StepKind.BIOPSY, StepKind.BLOODS, StepKind.SCAN,
        StepKind.PATHOLOGY_REPORT, StepKind.RADIOLOGY_REPORT, StepKind.REVIEW_CONSULT,
        StepKind.TREATMENT,
    )
    history = tuple(
        CareStep(id=f"{ANITA_ID}-{kind.value}", patient_id=ANITA_ID, kind=kind,
                 status=StepStatus.COMPLETED, completed_on=long_ago, queue=kind.value)
        for kind in history_kinds
    )
    steps = history + (
        CareStep(id=f"{ANITA_ID}-{StepKind.ECHO_REVIEW.value}", patient_id=ANITA_ID,
                 kind=StepKind.ECHO_REVIEW, status=StepStatus.SCHEDULED,
                 scheduled_for=echo_day, queue="cardiology", resource_id=ECHO_CARDIOLOGIST),
        CareStep(id=f"{ANITA_ID}-{StepKind.MAINTENANCE_DOSE.value}", patient_id=ANITA_ID,
                 kind=StepKind.MAINTENANCE_DOSE, status=StepStatus.SCHEDULED,
                 scheduled_for=dose_day, queue="day_care", resource_id=DAY_CARE_PHARMACY),
    )
    truth = GroundTruth(
        patient_id=ANITA_ID, true_ready_on={}, naive_return_date=dose_day,
        naive_target_step_id=f"{ANITA_ID}-{StepKind.MAINTENANCE_DOSE.value}",
    )
    cycle = MaintenanceCycle(
        patient_id=ANITA_ID, dose_index=13, anchor_date=dose_day - timedelta(days=21 * 12),
        requires_echo=True,
    )
    return patient, steps, truth, cycle


def build_scripted_cohort(
    n_patients: int = 48, seed: int = 20260925, today: date | None = None
) -> tuple[SyntheticCohort, MaintenanceCycle]:
    """The default 50-family cohort, minus two slots, plus Shambhu and Anita.

    Returns the cohort and Anita's `MaintenanceCycle` — the one piece of
    scripted state that isn't a `SyntheticCohort` field.
    """
    today = today or date.today()
    base = generate_cohort(n_patients=n_patients, seed=seed, today=today)

    shambhu, shambhu_steps, shambhu_truth = seed_shambhu_prasad(today)
    anita, anita_steps, anita_truth, cycle = seed_anita_devi(today)

    patients = (*base.patients, shambhu, anita)
    steps = {**base.steps, shambhu.id: shambhu_steps, anita.id: anita_steps}
    ground_truth = {**base.ground_truth, shambhu.id: shambhu_truth, anita.id: anita_truth}

    cohort = SyntheticCohort(
        patients=patients, steps=steps, turnaround=base.turnaround, ground_truth=ground_truth
    )
    return cohort, cycle


#: The "press advance" beats for each story, in the order the brief narrates
#: them. Each beat calls a real `LiveRunner` method — see
#: `LiveRunner.advance_story` — so advancing the story is a sequencing
#: convenience over genuine code paths, never a scripted fake of them.
#:
#: `actor` and `lane` are presentation only: they tell the story view which
#: row to drop the dot into and whose screen to point at. They do not affect
#: what runs. The clock times in `at` are the brief's narration; the durations
#: the console shows are the real measured ones.


@dataclass(frozen=True)
class StoryBeat:
    """One press of Advance."""

    action: str
    params: dict
    #: Who does this, as the brief's table names them.
    actor: str
    #: Which lane of the story view: family | agents | desk | decision.
    lane: str
    #: One line a presenter can read out.
    headline: str
    #: The brief's clock time for this beat, for narration only.
    at: str = ""

    def to_json(self) -> dict:
        return {
            "action": self.action,
            "actor": self.actor,
            "lane": self.lane,
            "headline": self.headline,
            "at": self.at,
            "patient_id": self.params.get("patient_id"),
        }


SHAMBHU_BEATS: tuple[StoryBeat, ...] = (
    StoryBeat(
        action="disrupt",
        params={
            "resource_id": MRI_2, "kind": DisruptionKind.MACHINE_DOWN, "days": 4,
            "note": "MRI-2 out of service",
        },
        actor="Imran Shaikh · radiology desk",
        lane="desk",
        headline="MRI-2 marked out of service. Every family booked on it is held.",
        at="7:40 am",
    ),
    StoryBeat(
        action="inbound",
        params={"patient_id": SHAMBHU_ID, "kind": "chasing"},
        actor="Vikash · caregiver",
        lane="family",
        headline="Vikash writes back. The caregiver actor composes it; the guard reads it.",
        at="7:44 am",
    ),
    StoryBeat(
        action="approve_first_option",
        params={
            "patient_id": SHAMBHU_ID, "role": Role.NAVIGATOR, "approved_by": "Seema Kamble",
        },
        actor="Seema Kamble · navigator",
        lane="decision",
        headline="Seema approves the option that keeps the stay the same length.",
        at="9:04 am",
    ),
    StoryBeat(
        action="confirm",
        params={"patient_id": SHAMBHU_ID},
        actor="Vikash, then Shambhu",
        lane="family",
        headline="Vikash confirms; Shambhu hears the new plan on the voice line.",
        at="9:20 am",
    ),
)

ANITA_BEATS: tuple[StoryBeat, ...] = (
    StoryBeat(
        action="disrupt",
        params={
            "resource_id": ECHO_CARDIOLOGIST, "kind": DisruptionKind.STAFF_UNAVAILABLE,
            "days": 7, "note": "the hub's only echo cardiologist is on emergency leave",
        },
        actor="Sanjay Verma · cardiology desk",
        lane="desk",
        headline="The hub's only echo cardiologist is away. Cover starts in a week.",
        at="4:10 pm",
    ),
    StoryBeat(
        action="inbound",
        params={"patient_id": ANITA_ID, "kind": "process_question"},
        actor="Priya · daughter",
        lane="family",
        headline="Priya writes in. Whatever she asks, the guard decides what may be answered.",
        at="4:22 pm",
    ),
    StoryBeat(
        action="approve_first_option",
        params={"patient_id": ANITA_ID, "role": Role.DOCTOR, "approved_by": "Dr Amrita Sinha"},
        actor="Dr Amrita Sinha · oncologist",
        lane="decision",
        headline="Dr Sinha picks the option that keeps the same lab for comparison.",
        at="5:52 pm",
    ),
    StoryBeat(
        action="disrupt",
        params={
            "resource_id": DAY_CARE_PHARMACY, "kind": DisruptionKind.STOCK_DELAY,
            "days": 7, "note": "Monday's drug delivery has not arrived",
        },
        actor="Rekha Kumari · day-care desk",
        lane="desk",
        headline="The drug delivery has not arrived. Next supply is a week out.",
        at="11:20 am",
    ),
    StoryBeat(
        action="approve_first_option",
        params={"patient_id": ANITA_ID, "role": Role.DOCTOR, "approved_by": "Dr Amrita Sinha"},
        actor="Dr Amrita Sinha · oncologist",
        lane="decision",
        headline="Two trips become one: the dose moves to the day she is already at the hub.",
        at="12:05 pm",
    ),
    StoryBeat(
        action="confirm",
        params={"patient_id": ANITA_ID},
        actor="Manoj, then Priya",
        lane="family",
        headline="Manoj presses 1 on the voice call; Priya replies on WhatsApp.",
        at="12:14 pm",
    ),
)

STORY_BEATS: dict[str, tuple[StoryBeat, ...]] = {
    "shambhu": SHAMBHU_BEATS,
    "anita": ANITA_BEATS,
}

#: What a presenter picks between, for the story bar.
STORIES: tuple[dict, ...] = (
    {
        "id": "shambhu",
        "title": "The MRI machine fails on the morning of the scan",
        "patient_id": SHAMBHU_ID,
        "who": "Shambhu Prasad · Gaya, Bihar · before treatment",
    },
    {
        "id": "anita",
        "title": "The hub's only echo doctor is called away",
        "patient_id": ANITA_ID,
        "who": "Anita Devi · Samastipur, Bihar · maintenance",
    },
)
