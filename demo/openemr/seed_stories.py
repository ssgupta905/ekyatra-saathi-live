"""Four more families, each carrying a different reason a journey goes wrong.

The four already seeded (`bahmni_seed.PATIENTS`) all fail the same way: a
doctor goes on leave and their visit is in the way. That is one story told
four times, and a demo of it shows breadth of language rather than breadth of
judgement. These four fail differently, so one change at the hospital produces
four different answers — which is the thing actually worth watching.

    MEERA     maintenance chemo, 21-day interval, echo due with the dose.
              Asks to delay ten days. The dose cannot move that far, so she
              is offered three days EARLIER instead — doing what was asked is
              not the same as helping.

    JOSEPHINE scan done, radiology report not back. If she travels on the
              booked day she makes the journey for nothing, and the answer is
              to hold the visit rather than move it.

    ARUN      lives 25km away, not 1,000. The same disruption that strands
              Shambhu for two days costs Arun an afternoon, and the planner
              is supposed to know the difference: `gap_days` decides whether
              a family waits in the city or goes home between visits.

    PRIYA     two steps that can share one trip. Instead of three journeys
              the planner puts the bloods and the review on the scan's day.

Both halves are written, on purpose. The hospital gets the patient and the
booking over FHIR, because the connector finds families by the identifier
OpenEMR holds and a family it cannot find is a family a leave cannot reach.
Our own records get the steps, through the Console's own records API, because
that is how a desk enters them.

    python demo/openemr/seed_stories.py --check        # say what it would do
    python demo/openemr/seed_stories.py --write \
        --api https://…onrender.com --base-url http://…:8300 --key …pem

Nothing here invents a clinical fact. Every step kind, every dependency and
every bundling rule comes from `domain/pathway.py`'s solid-tumour pathway;
this only chooses which families are standing where on it.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, time, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from saathi.bootstrap.bahmni_seed import SeedAppointment, SeedPatient  # noqa: E402
from saathi.bootstrap.openemr_seed import (  # noqa: E402
    Client,
    _facility,
    _practitioner,
    _token,
    ensure_appointments,
    ensure_patients,
)


@dataclass(frozen=True)
class Story:
    """One family, their hospital record, and where they stand on the pathway."""

    patient: SeedPatient
    #: Our own record: district, how far, which language, which hospital.
    district: str
    #: Required by the records API. Deliberately unreachable — see PHONES.
    distance_km: float
    language: str
    #: Steps as `(kind, status, days_from_today or None)`.
    steps: tuple[tuple[str, str, int | None], ...]
    #: The hospital booking that makes them reachable by a leave.
    appointment: SeedAppointment
    why: str


PREFIX = "EKY-"

#: Caregiver numbers. The 99999-0xxxx block is not allocated to any subscriber,
#: so a demo that sends a message cannot reach a real person by mistake. A
#: plausible-looking real number here is one typo away from texting a stranger
#: about cancer treatment.
PHONES = {
    f"{PREFIX}MEERA": "+919999901001",
    f"{PREFIX}JOSEPHINE": "+919999901002",
    f"{PREFIX}ARUN": "+919999901003",
    f"{PREFIX}PRIYA": "+919999901004",
}

STORIES: tuple[Story, ...] = (
    Story(
        patient=SeedPatient(f"{PREFIX}MEERA", "Meera", "Yadav", "F", "1968-06-21", "Gaya"),
        district="Gaya",
        distance_km=1020.0,
        language="hi",
        steps=(
            ("consult", "completed", -84),
            ("biopsy", "completed", -77),
            ("pathology_report", "result_available", -70),
            ("treatment", "completed", -42),
            # The dose, and the echo that has to happen with it.
            ("maintenance_dose", "scheduled", 3),
            ("echo_review", "scheduled", 3),
        ),
        appointment=SeedAppointment(f"{PREFIX}MEERA", "Echo cardiologist", 3, time(9, 30)),
        why="a maintenance dose that cannot move ten days, so it moves three the other way",
    ),
    Story(
        patient=SeedPatient(
            f"{PREFIX}JOSEPHINE", "Josephine", "Lakra", "F", "1983-02-14", "Ranchi"
        ),
        district="Ranchi",
        distance_km=1340.0,
        language="hi",
        steps=(
            ("consult", "completed", -30),
            ("scan", "completed", -5),
            # Not back. Travelling on the booked day wastes the journey.
            ("radiology_report", "not_scheduled", None),
            ("review_consult", "scheduled", 2),
        ),
        appointment=SeedAppointment(f"{PREFIX}JOSEPHINE", "MRI machine 2", 2, time(12, 0)),
        why="a report that is not back, so the visit is held rather than moved",
    ),
    Story(
        patient=SeedPatient(f"{PREFIX}ARUN", "Arun", "Kamble", "M", "1975-09-08", "Thane"),
        district="Thane",
        distance_km=25.0,
        language="en",
        steps=(
            ("consult", "completed", -21),
            ("bloods", "completed", -7),
            ("review_consult", "scheduled", 4),
        ),
        appointment=SeedAppointment(f"{PREFIX}ARUN", "MRI machine 1", 4, time(14, 30)),
        why="25km away, so waiting in the city is the wrong advice for him",
    ),
    Story(
        patient=SeedPatient(f"{PREFIX}PRIYA", "Priya", "Nair", "F", "1990-12-02", "Mirzapur"),
        district="Mirzapur",
        distance_km=1180.0,
        language="hi",
        steps=(
            ("consult", "completed", -28),
            ("scan", "scheduled", 5),
            ("bloods", "scheduled", 9),
            ("review_consult", "scheduled", 12),
        ),
        appointment=SeedAppointment(f"{PREFIX}PRIYA", "MRI machine 1", 5, time(11, 0)),
        why="three journeys the planner can make into one",
    ),
)


def _day(today: date, offset: int | None) -> str | None:
    return None if offset is None else (today + timedelta(days=offset)).isoformat()


def write_our_records(api: str, story: Story, today: date, *, write: bool) -> list[str]:
    """Register the family and their steps the way a desk does, through the API."""
    did: list[str] = []
    patient = {
        "id": story.patient.identifier,
        "name": f"{story.patient.given_name} {story.patient.family_name}",
        "home_district": story.district,
        "home_distance_km": story.distance_km,
        "language": story.language,
        "hospital_id": "TMH-MUM",
        "pathway_id": "oncology",
        "caregiver_phone": PHONES[story.patient.identifier],
    }
    if not write:
        did.append(f"would register {patient['id']} ({story.district}, {story.distance_km:.0f}km)")
        for kind, status, offset in story.steps:
            did.append(f"  would add {kind} [{status}] {_day(today, offset) or 'unscheduled'}")
        return did

    with httpx.Client(base_url=api.rstrip("/"), timeout=90.0) as client:
        response = client.post("/api/patients", json=patient)
        if response.status_code == 409:
            did.append(f"{patient['id']} is already on record")
        elif response.status_code >= 400:
            did.append(
                f"FAILED to register {patient['id']}: "
                f"{response.status_code} {response.text[:160]}"
            )
            return did
        else:
            did.append(f"registered {patient['id']}")

        for kind, status, offset in story.steps:
            step = {"kind": kind, "status": status, "scheduled_for": _day(today, offset)}
            if status == "completed":
                step["completed_on"] = _day(today, offset)
                step["scheduled_for"] = None
            if status == "result_available":
                step["result_available_on"] = _day(today, offset)
                step["scheduled_for"] = None
            got = client.post(f"/api/patients/{patient['id']}/steps", json=step)
            if got.status_code >= 400:
                did.append(f"  FAILED {kind}: {got.status_code} {got.text[:120]}")
            else:
                did.append(f"  added {kind} [{status}]")
    return did


def write_the_hospital(
    base_url: str, client_id: str, key_id: str, key_path: str, today: date, *, write: bool
) -> list[str]:
    """Register these families with the hospital and book their visits.

    Without this the connector cannot find them: it matches a hospital
    appointment to one of our families by the identifier OpenEMR holds, so a
    family with no record there is a family no leave can reach. Through the
    same functions the standing cast uses, with this cast passed in.
    """
    token = _token(base_url, client_id, key_id, key_path)
    client = Client(base_url=base_url, token=token, write=write)
    patients = ensure_patients(client, cast=[s.patient for s in STORIES])
    booked = ensure_appointments(
        client,
        patients,
        facility=_facility(client),
        practitioner=_practitioner(client),
        today=today,
        cast=[s.appointment for s in STORIES],
    )
    return [*client.did, *(f"would {line}" for line in client.would)] or [
        f"{len(booked)} booking(s) already stood"
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="actually create things")
    parser.add_argument("--check", action="store_true", help="say what is there and stop")
    parser.add_argument("--api", default=None, help="the deployed API, for our own records")
    parser.add_argument("--today", default=None, help="YYYY-MM-DD; defaults to the real today")
    parser.add_argument("--base-url", default=None, help="the hospital, e.g. http://8.231.81.219:8300")
    parser.add_argument("--client-id", default=None)
    parser.add_argument("--key-id", default=None)
    parser.add_argument("--key", default="demo/openemr/openemr-key-vm.pem")
    args = parser.parse_args(argv)

    today = date.fromisoformat(args.today) if args.today else date.today()
    print(f"  today is {today}\n")
    for story in STORIES:
        print(f"  {story.patient.identifier}: {story.why}")
        print(f"    {story.district}, {story.distance_km:.0f}km, {story.language}")
        booked = _day(today, story.appointment.days_from_today)
        print(
            f"    hospital booking: {story.appointment.service_name} "
            f"on {booked} at {story.appointment.at}"
        )
        if args.api:
            written = write_our_records(
                args.api, story, today, write=args.write and not args.check
            )
            for line in written:
                print(f"    {line}")
        print()

    if not args.api:
        print("  --api was not given, so nothing was written to our own records.")

    if args.base_url and args.client_id and args.key_id:
        print("  the hospital:")
        for line in write_the_hospital(
            args.base_url, args.client_id, args.key_id, args.key, today,
            write=args.write and not args.check,
        ):
            print(f"    {line}")
    else:
        print("  --base-url, --client-id and --key-id were not all given, so the")
        print("  hospital knows nothing about these families and no leave can reach them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
