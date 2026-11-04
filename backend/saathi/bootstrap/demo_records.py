"""A starter cohort for a fresh real-world database.

A deployment that starts empty is correct and also useless to look at. With
`SAATHI_SEED_DEMO=true` an *empty* database is given a small synthetic cohort,
entered through the same record store a desk's entries go through, so from then
on these are ordinary records: planned, edited and kept like any other.

It never runs against a database that already holds a family, and it is not the
demo world: nothing here is simulated after the fact, and the clock is the real one.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from ..config import Settings
from ..domain.enums import (
    Language,
    ReadinessKind,
    ReadinessStatus,
    ResourceKind,
    SourceSystem,
    StepKind,
    StepStatus,
)
from ..domain.models import CareStep, Patient, ReadinessItem, Resource
from ..ports.records import RecordStore, TurnaroundObservation
from ..synthetic.generate import generate_cohort

logger = logging.getLogger(__name__)

#: Enough to fill the screens and give the readiness forecast something to learn
#: from, few enough to read at a glance.
SEED_FAMILIES = 12


def seed_demo_records(store: RecordStore, today: date, settings: Settings) -> bool:
    """Fill an empty database. True when it seeded, False when it left things alone."""
    if store.load().patients:
        return False

    cohort = generate_cohort(n_patients=SEED_FAMILIES, today=today)
    phone = settings.seed_demo_phone
    for index, patient in enumerate(cohort.patients):
        if index == 0 and phone:
            # So a person can sign in as this family: their phone gets the code.
            patient = patient.model_copy(
                update={
                    "caregiver_phone": phone,
                    "family_members": tuple(
                        m.model_copy(update={"phone": phone}) for m in patient.family_members
                    ),
                }
            )
        store.save_patient(patient)
        for step in cohort.steps.get(patient.id, ()):
            store.save_step(step)

    # The forecast is calibrated only on releases the system has seen. History,
    # dated before today, is what lets a queue say something other than "not yet".
    for number, sample in enumerate(cohort.turnaround):
        store.add_turnaround(
            TurnaroundObservation(
                queue=sample.queue,
                days=sample.days,
                observed_on=today - timedelta(days=1 + number % 60),
                hospital_id="TMH-MUM",
            )
        )
    logger.info("seeded %d synthetic families into an empty database", len(cohort.patients))
    return True


def apply_demo_contacts(store: RecordStore, settings: Settings) -> bool:
    """Point the first seeded family at the email in configuration.

    Done on every start, not only the first, so an email added to configuration
    later reaches a database that was seeded long before. True when it changed one.
    """
    email = (settings.seed_demo_email or "").strip().lower()
    if not email:
        return False
    first = next((p for p in store.load().patients if p.id == FIRST_FAMILY), None)
    if first is None or first.caregiver_email == email:
        return False
    store.save_patient(first.model_copy(update={"caregiver_email": email}))
    logger.info("the first seeded family now answers to the demo email")
    return True


#: The family `seed_demo_phone` and `seed_demo_email` are attached to.
FIRST_FAMILY = "P0000"

#: Showcase families carry this prefix, so topping up never mistakes them for
#: anyone else's records and never adds them twice.
SHOWCASE_PREFIX = "SHOW-"
_HOSPITAL = "TMH-MUM"


def seed_showcase(store: RecordStore, today: date) -> bool:
    """Add what the starter cohort lacks: other pathways, hospital resources and
    the other parties in a journey. Additive and idempotent, so it also tops up a
    database seeded before this existed. True when it added anything.

    Everything here is invented for the demonstration and is logistics only: a
    status, a party, a date. Nothing says what a medicine is or what a report found.
    """
    if any(p.id.startswith(SHOWCASE_PREFIX) for p in store.load().patients):
        return False

    for resource in (
        Resource(id="MRI-2", kind=ResourceKind.MACHINE, display_name="MRI-2",
                 hospital_id=_HOSPITAL, department="scan"),
        Resource(id="DIALYSIS-3", kind=ResourceKind.MACHINE, display_name="Dialysis machine 3",
                 hospital_id=_HOSPITAL, department="dialysis_session"),
        Resource(id="ECHO-CARDIOLOGIST", kind=ResourceKind.STAFF,
                 display_name="Echo cardiologist", hospital_id=_HOSPITAL,
                 department="echo_review"),
    ):
        store.save_resource(resource)

    tomorrow = today + timedelta(days=1)
    earlier = today - timedelta(days=6)

    def family(pid, name, district, km, language, phone, pathway="oncology", abha=None):
        store.save_patient(
            Patient(id=pid, name=name, abha_number=abha, home_district=district,
                    home_distance_km=km, language=language, caregiver_phone=phone,
                    hospital_id=_HOSPITAL, pathway_id=pathway)
        )

    def step(pid, kind, status, *, on=None, resource=None, released=None):
        store.save_step(
            CareStep(id=f"{pid}-{kind.value}", patient_id=pid, kind=kind, status=status,
                     scheduled_for=on, completed_on=earlier if status in _DONE else None,
                     result_available_on=released, queue=kind.value, resource_id=resource)
        )

    def ready_oncology(pid):
        """Everything the review consult needs is done: a GO until a party says otherwise."""
        for kind in (StepKind.CONSULT, StepKind.BIOPSY, StepKind.BLOODS, StepKind.SCAN):
            step(pid, kind, StepStatus.COMPLETED, on=earlier)
        for kind in (StepKind.PATHOLOGY_REPORT, StepKind.RADIOLOGY_REPORT):
            step(pid, kind, StepStatus.RESULT_AVAILABLE, released=earlier)
        step(pid, StepKind.REVIEW_CONSULT, StepStatus.SCHEDULED, on=today + timedelta(days=2))

    def party(pid, kind, who, status, *, alt=False, detail=""):
        store.save_readiness_item(
            ReadinessItem(id=f"{pid}-{kind.value}", patient_id=pid, kind=kind, party=who,
                          status=status, alternative_available=alt, detail=detail,
                          source=SourceSystem.PARTNER)
        )

    # Other conditions, same engine: a dialysis family that can go, one still
    # waiting on bloods, and a family home from hospital.
    family("SHOW-DIA-1", "Sunita Devi", "Gaya", 1010.0, Language.HINDI, "+919000000011",
           "dialysis", "91-1000-0000-0011")
    step("SHOW-DIA-1", StepKind.BLOODS, StepStatus.COMPLETED, on=earlier)
    step("SHOW-DIA-1", StepKind.NEPHROLOGY_REVIEW, StepStatus.COMPLETED, on=earlier)
    step("SHOW-DIA-1", StepKind.DIALYSIS_SESSION, StepStatus.SCHEDULED, on=tomorrow,
         resource="DIALYSIS-3")

    family("SHOW-DIA-2", "Ramesh Yadav", "Siwan", 1120.0, Language.HINDI, "+919000000012",
           "dialysis")
    step("SHOW-DIA-2", StepKind.NEPHROLOGY_REVIEW, StepStatus.COMPLETED, on=earlier)
    step("SHOW-DIA-2", StepKind.BLOODS, StepStatus.SCHEDULED, on=today)
    step("SHOW-DIA-2", StepKind.DIALYSIS_SESSION, StepStatus.SCHEDULED, on=tomorrow,
         resource="DIALYSIS-3")

    family("SHOW-POST-1", "Mohan Lal", "Hajipur", 1090.0, Language.HINDI, "+919000000013",
           "post_discharge")
    step("SHOW-POST-1", StepKind.BLOODS, StepStatus.COMPLETED, on=earlier)
    step("SHOW-POST-1", StepKind.WOUND_CHECK, StepStatus.COMPLETED, on=earlier)
    step("SHOW-POST-1", StepKind.DISCHARGE_REVIEW, StepStatus.SCHEDULED, on=tomorrow)

    # Two families booked on MRI-2 tomorrow: report it down and both are affected.
    for pid, name, district, km in (
        ("SHOW-MRI-1", "Shambhu Prasad", "Gaya", 1030.0),
        ("SHOW-MRI-2", "Kavita Das", "Nadia", 1900.0),
    ):
        family(pid, name, district, km, Language.HINDI if pid.endswith("1") else Language.BENGALI,
               "+919000000014" if pid.endswith("1") else "+919000000015")
        step(pid, StepKind.CONSULT, StepStatus.COMPLETED, on=earlier)
        step(pid, StepKind.BIOPSY, StepStatus.COMPLETED, on=earlier)
        step(pid, StepKind.BLOODS, StepStatus.COMPLETED, on=earlier)
        for kind in (StepKind.PATHOLOGY_REPORT, StepKind.RADIOLOGY_REPORT):
            step(pid, kind, StepStatus.RESULT_AVAILABLE, released=earlier)
        step(pid, StepKind.SCAN, StepStatus.SCHEDULED, on=tomorrow, resource="MRI-2")
        step(pid, StepKind.REVIEW_CONSULT, StepStatus.SCHEDULED, on=today + timedelta(days=3))

    # The other parties. Each family is ready on the care steps, so the only
    # thing in the way is a party, which is the point of showing them.
    family("SHOW-GO-1", "Anita Kumari", "Purnia", 2008.0, Language.HINDI, "+919000000016",
           abha="91-1000-0000-0016")
    ready_oncology("SHOW-GO-1")
    party("SHOW-GO-1", ReadinessKind.TRANSPORT, "Uber", ReadinessStatus.READY,
          detail="cab booked for 6 am")
    party("SHOW-GO-1", ReadinessKind.STAY, "OYO", ReadinessStatus.READY,
          detail="two nights near the hospital")

    family("SHOW-WAIT-1", "Geeta Kumari", "Purnia", 1955.0, Language.HINDI, "+919000000017",
           abha="91-1000-0000-0017")
    ready_oncology("SHOW-WAIT-1")
    party("SHOW-WAIT-1", ReadinessKind.MEDICINE, "day-care pharmacy", ReadinessStatus.PENDING,
          detail="stock arrives tomorrow")

    family("SHOW-REPLAN-1", "Imtiyaz Ansari", "Nadia", 1940.0, Language.BENGALI,
           "+919000000018", abha="91-1000-0000-0018")
    ready_oncology("SHOW-REPLAN-1")
    party("SHOW-REPLAN-1", ReadinessKind.TRANSPORT, "Ola", ReadinessStatus.BLOCKED,
          alt=True, detail="driver cancelled; another cab is free")

    family("SHOW-UNSURE-1", "Lakshmi Behera", "Cuttack", 1665.0, Language.ODIA,
           "+919000000019", abha="91-1000-0000-0019")
    ready_oncology("SHOW-UNSURE-1")
    party("SHOW-UNSURE-1", ReadinessKind.INSURANCE, "PM-JAY desk", ReadinessStatus.UNKNOWN,
          detail="no answer yet on the pre-authorisation")

    logger.info("added the showcase families, resources and partner statuses")
    return True


_DONE = frozenset({StepStatus.COMPLETED, StepStatus.RESULT_AVAILABLE})
