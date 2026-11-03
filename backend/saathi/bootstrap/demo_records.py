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
