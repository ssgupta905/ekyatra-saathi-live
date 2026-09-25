"""Synthetic patients with planted ground truth.

The prototype cannot be evaluated on real families, so it is evaluated on
synthetic ones where we know the answer. For each patient we generate:

* a journey of care steps,
* a turnaround history for the queues that journey touches,
* and the *true* date each pending report actually lands.

The last one is the planted ground truth. It lets us ask the only question that
matters: if the family had travelled on the date the hospital gave them, would
the step have been possible? Every "no" is a wasted trip — a real bus fare, a
night on a footpath, a day of lost wages — and the number Saathi is trying to
drive down.

Generation is seeded and deterministic, so a demo run is reproducible.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from ..domain.enums import Language, StepKind, StepStatus
from ..domain.models import CareStep, Patient
from ..readiness.conformal import TurnaroundSample

#: Turnaround profiles per queue: (median days, heavy-tail probability, tail days).
#: Pathology is slower and far more variable than radiology, which is exactly
#: why a single "reports take a week" rule strands families.
QUEUE_PROFILES: dict[str, tuple[float, float, float]] = {
    "pathology_report": (7.0, 0.20, 9.0),
    "radiology_report": (3.0, 0.10, 5.0),
}

DISTRICTS = (
    ("Balasore", "or", 1450.0),
    ("Murshidabad", "bn", 1900.0),
    ("Gorakhpur", "hi", 1700.0),
    ("Purnia", "hi", 2000.0),
    ("Cuttack", "or", 1650.0),
    ("Nadia", "bn", 1950.0),
    ("Darbhanga", "hi", 1850.0),
)


@dataclass(frozen=True)
class GroundTruth:
    """What actually happened, hidden from the planner."""

    patient_id: str
    #: step_id -> the date the report genuinely became available.
    true_ready_on: dict[str, date]
    #: The date the hospital naively told the family to come back.
    naive_return_date: date
    #: step_id of the visit that date was for.
    naive_target_step_id: str


@dataclass(frozen=True)
class SyntheticCohort:
    patients: tuple[Patient, ...]
    steps: dict[str, tuple[CareStep, ...]]
    turnaround: tuple[TurnaroundSample, ...]
    ground_truth: dict[str, GroundTruth]


def _turnaround_days(rng: random.Random, queue: str) -> float:
    median, tail_p, tail_extra = QUEUE_PROFILES[queue]
    days = max(1.0, rng.gauss(median, median * 0.25))
    if rng.random() < tail_p:
        # The tail is the whole problem: a slow week in the lab is what turns a
        # planned visit into a wasted one.
        days += abs(rng.gauss(tail_extra, tail_extra * 0.4))
    return round(days)


def generate_turnaround_history(
    rng: random.Random, per_queue: int = 120
) -> tuple[TurnaroundSample, ...]:
    samples: list[TurnaroundSample] = []
    for queue in QUEUE_PROFILES:
        for _ in range(per_queue):
            samples.append(TurnaroundSample(queue=queue, days=_turnaround_days(rng, queue)))
    return tuple(samples)


def generate_patient(
    rng: random.Random, index: int, today: date
) -> tuple[Patient, tuple[CareStep, ...], GroundTruth]:
    district, lang, distance = rng.choice(DISTRICTS)
    patient_id = f"P{index:04d}"
    patient = Patient(
        id=patient_id,
        home_distance_km=distance + rng.uniform(-80, 80),
        home_district=district,
        language=Language(lang),
        caregiver_phone=f"+9199{rng.randint(10_000_000, 99_999_999)}",
        hospital_id="TMH-MUM",
    )

    # First trip: consult, biopsy and bloods done together.
    first_visit = today - timedelta(days=rng.randint(4, 12))
    steps: list[CareStep] = [
        CareStep(
            id=f"{patient_id}-consult",
            patient_id=patient_id,
            kind=StepKind.CONSULT,
            status=StepStatus.COMPLETED,
            scheduled_for=first_visit,
            completed_on=first_visit,
            queue="consult",
        ),
        CareStep(
            id=f"{patient_id}-biopsy",
            patient_id=patient_id,
            kind=StepKind.BIOPSY,
            status=StepStatus.COMPLETED,
            scheduled_for=first_visit,
            completed_on=first_visit,
            queue="biopsy",
        ),
        CareStep(
            id=f"{patient_id}-bloods",
            patient_id=patient_id,
            kind=StepKind.BLOODS,
            status=StepStatus.COMPLETED,
            scheduled_for=first_visit,
            completed_on=first_visit,
            queue="bloods",
        ),
        CareStep(
            id=f"{patient_id}-scan",
            patient_id=patient_id,
            kind=StepKind.SCAN,
            status=StepStatus.COMPLETED,
            scheduled_for=first_visit,
            completed_on=first_visit,
            queue="scan",
        ),
    ]

    true_ready: dict[str, date] = {}
    for kind, queue in (
        (StepKind.PATHOLOGY_REPORT, "pathology_report"),
        (StepKind.RADIOLOGY_REPORT, "radiology_report"),
    ):
        actual_days = _turnaround_days(rng, queue)
        ready_on = first_visit + timedelta(days=int(actual_days))
        step_id = f"{patient_id}-{queue}"
        true_ready[step_id] = ready_on

        landed = ready_on <= today
        steps.append(
            CareStep(
                id=step_id,
                patient_id=patient_id,
                kind=kind,
                status=StepStatus.RESULT_AVAILABLE if landed else StepStatus.PENDING_RESULT,
                completed_on=first_visit,
                result_available_on=ready_on if landed else None,
                queue=queue,
            )
        )

    # The review consult the family is waiting for.
    review_id = f"{patient_id}-review"
    # The naive hospital practice: "come back in a week" from the first visit,
    # with no reference to whether the reports will be ready.
    naive_return = first_visit + timedelta(days=7)
    steps.append(
        CareStep(
            id=review_id,
            patient_id=patient_id,
            kind=StepKind.REVIEW_CONSULT,
            status=StepStatus.SCHEDULED,
            scheduled_for=naive_return,
            queue="review_consult",
        )
    )

    return (
        patient,
        tuple(steps),
        GroundTruth(
            patient_id=patient_id,
            true_ready_on=true_ready,
            naive_return_date=naive_return,
            naive_target_step_id=review_id,
        ),
    )


def generate_cohort(
    n_patients: int = 50, seed: int = 20260925, today: date | None = None
) -> SyntheticCohort:
    rng = random.Random(seed)
    today = today or date.today()

    patients: list[Patient] = []
    steps: dict[str, tuple[CareStep, ...]] = {}
    truth: dict[str, GroundTruth] = {}

    for i in range(n_patients):
        patient, patient_steps, ground_truth = generate_patient(rng, i, today)
        patients.append(patient)
        steps[patient.id] = patient_steps
        truth[patient.id] = ground_truth

    return SyntheticCohort(
        patients=tuple(patients),
        steps=steps,
        turnaround=generate_turnaround_history(rng),
        ground_truth=truth,
    )


def would_be_wasted(ground_truth: GroundTruth, travel_on: date) -> bool:
    """True if travelling on `travel_on` means arriving before the reports land."""
    if not ground_truth.true_ready_on:
        return False
    return travel_on < max(ground_truth.true_ready_on.values())


#: Mean non-medical spend per trip, from the IIPS / Tata Memorial Centre study
#: (Journal of Cancer Policy, 2025): mean total non-medical cost of Rs 88,433
#: across a course of treatment. This is the per-trip share used for the
#: prototype's cost-avoided figure; the pilot replaces it with measured spend.
COST_PER_WASTED_TRIP_INR = 8_500.0


def evaluate(
    cohort: SyntheticCohort,
    decisions: dict[str, date | None],
) -> dict[str, float]:
    """Score Saathi's plans against the naive baseline.

    `decisions` maps patient_id -> the date Saathi told them to travel, or None
    when it said wait / gave no date.
    """
    baseline_wasted = 0
    saathi_wasted = 0
    trips_avoided = 0

    for patient_id, truth in cohort.ground_truth.items():
        baseline_wastes = would_be_wasted(truth, truth.naive_return_date)

        travel_on = decisions.get(patient_id)
        # A family told to wait takes no trip, so it wastes none. A family told
        # to travel wastes one only if it still arrives before the reports land.
        saathi_wastes = travel_on is not None and would_be_wasted(truth, travel_on)

        if baseline_wastes:
            baseline_wasted += 1
        if saathi_wastes:
            saathi_wasted += 1
        # Credit a saved trip whether Saathi withheld the date or moved it to a
        # safe one — both spare the family the same journey.
        if baseline_wastes and not saathi_wastes:
            trips_avoided += 1

    n = len(cohort.ground_truth) or 1
    return {
        "patients": float(n),
        "baseline_wasted_trips": float(baseline_wasted),
        "saathi_wasted_trips": float(saathi_wasted),
        "wasted_trips_avoided": float(trips_avoided),
        "baseline_waste_rate": baseline_wasted / n,
        "saathi_waste_rate": saathi_wasted / n,
        "non_medical_cost_avoided_inr": trips_avoided * COST_PER_WASTED_TRIP_INR,
    }
