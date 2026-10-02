"""The two demo families from the team brief, seeded onto real steps.

`seed_shambhu_prasad` and `seed_anita_devi` do not touch the 50-family
cohort `generate.py` produces — `build_scripted_cohort` appends them to it,
so the existing demo (`make demo`, the default live world) is unaffected.
Dates, resource names and numbers echo the brief closely enough to narrate
on stage; they are still synthetic, same as the rest of this module's cohort.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..domain.enums import DisruptionKind, Language, Role, StepKind, StepStatus
from ..domain.models import CareStep, MaintenanceCycle, Patient
from .generate import GroundTruth, SyntheticCohort, generate_cohort

SHAMBHU_ID = "P-SHAMBHU"
ANITA_ID = "P-ANITA"

#: Resource ids the scripted disruptions are raised against. Registered on
#: the world so a desk can report them by name, the same as a real one would.
MRI_2 = "MRI-2"
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
                 status=StepStatus.SCHEDULED, scheduled_for=scan_day + timedelta(days=4),
                 queue="review_consult"),
    )
    truth = GroundTruth(
        patient_id=SHAMBHU_ID,
        true_ready_on={f"{SHAMBHU_ID}-radiology_report": scan_day + timedelta(days=1)},
        naive_return_date=scan_day + timedelta(days=4),
        naive_target_step_id=f"{SHAMBHU_ID}-review",
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
SHAMBHU_BEATS: tuple[tuple[str, dict], ...] = (
    ("disrupt", {
        "resource_id": MRI_2, "kind": DisruptionKind.MACHINE_DOWN, "days": 4,
        "note": "MRI-2 out of service",
    }),
    ("approve_first_option", {
        "patient_id": SHAMBHU_ID, "role": Role.NAVIGATOR, "approved_by": "Seema Kamble",
    }),
)

ANITA_BEATS: tuple[tuple[str, dict], ...] = (
    ("disrupt", {
        "resource_id": ECHO_CARDIOLOGIST, "kind": DisruptionKind.STAFF_UNAVAILABLE, "days": 7,
        "note": "the hub's only echo cardiologist is on emergency leave",
    }),
    ("approve_first_option", {
        "patient_id": ANITA_ID, "role": Role.DOCTOR, "approved_by": "Dr Amrita Sinha",
    }),
    ("disrupt", {
        "resource_id": DAY_CARE_PHARMACY, "kind": DisruptionKind.STOCK_DELAY, "days": 7,
        "note": "Monday's drug delivery has not arrived",
    }),
    ("approve_first_option", {
        "patient_id": ANITA_ID, "role": Role.DOCTOR, "approved_by": "Dr Amrita Sinha",
    }),
)

STORY_BEATS: dict[str, tuple[tuple[str, dict], ...]] = {
    "shambhu": SHAMBHU_BEATS,
    "anita": ANITA_BEATS,
}
