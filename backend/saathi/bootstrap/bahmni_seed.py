"""Put the demo's hospital into a real Bahmni, and leave everything else alone.

The demo needs a hospital that behaves like one: machines a slot can be booked
onto, families booked onto them, and a radiology desk that can cancel a slot.
Bahmni has all of that, under its own names — a machine is an *appointment
service*, a family is a *patient* with an identifier, and "the MRI is down" is
what happens to the appointments when a desk blocks the modality.

Three rules this script follows, because it runs against somebody's hospital.

**Idempotent.** Everything is looked up before it is created, and running it
twice changes nothing the second time. That is also what makes it a reset:
the demo's start state is whatever this script asserts.

**Additive and namespaced.** Nothing is ever deleted and nothing outside the
`EKY-` identifier prefix is touched. The public Bahmni demo is shared with
strangers, and some of them are mid-demonstration.

**Dry by default.** It prints what it would do and exits. Writing to a hospital
system — even a demo one — takes `--write`, typed on purpose.

The names matter and are not cosmetic: `HospitalLinks` in
`live/hospital_sync.py` matches an appointment to one of our families by
**identifier**, and to one of our resources by **service name**. So the
identifier written here is the patient id used in our own records, and the
service name is the resource's display name. Change one without the other and
the connector reads a hospital full of strangers.

    python -m saathi.bootstrap.bahmni_seed                  # say what it would do
    python -m saathi.bootstrap.bahmni_seed --write          # actually do it
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import httpx

from ..config import get_settings

logger = logging.getLogger("bahmni_seed")

#: Every identifier this script writes starts with this. Nothing without it is
#: ever read back as ours, created, or changed.
PREFIX = "EKY-"


@dataclass(frozen=True)
class SeedService:
    """A bookable thing. `name` must equal our `Resource.display_name`."""

    name: str
    speciality: str
    duration_minutes: int


@dataclass(frozen=True)
class SeedPatient:
    """A family. `identifier` must equal our `Patient.id`."""

    identifier: str
    given_name: str
    family_name: str
    gender: str
    birthdate: str
    village: str


@dataclass(frozen=True)
class SeedAppointment:
    """A booking, placed relative to today so the demo never goes stale."""

    patient_identifier: str
    service_name: str
    days_from_today: int
    at: time


#: The cast. Kamla is the story; the others are the ordinary noise that makes
#: the sorter's job visible — a board with one row on it proves nothing about
#: ordering.
SERVICES: tuple[SeedService, ...] = (
    SeedService("MRI machine 1", "Radiology", 30),
    SeedService("MRI machine 2", "Radiology", 30),
    SeedService("Echo cardiologist", "Cardiology", 30),
    SeedService("Dialysis station 3", "Nephrology", 240),
)

PATIENTS: tuple[SeedPatient, ...] = (
    SeedPatient(f"{PREFIX}KAMLA", "Kamla", "Devi", "F", "1964-04-12", "Gaya"),
    SeedPatient(f"{PREFIX}SHANTI", "Shanti", "Kumari", "F", "1971-08-03", "Darbhanga"),
    SeedPatient(f"{PREFIX}RAMESH", "Ramesh", "Prasad", "M", "1958-01-27", "Patna"),
    SeedPatient(f"{PREFIX}FATIMA", "Fatima", "Begum", "F", "1979-11-19", "Samastipur"),
)

APPOINTMENTS: tuple[SeedAppointment, ...] = (
    # The story: Kamla's MRI, the one a judge cancels.
    SeedAppointment(f"{PREFIX}KAMLA", "MRI machine 1", 3, time(10, 0)),
    # The noise, including the dialysis patient the panel also handles.
    SeedAppointment(f"{PREFIX}SHANTI", "MRI machine 2", 3, time(11, 30)),
    SeedAppointment(f"{PREFIX}RAMESH", "Dialysis station 3", 1, time(8, 0)),
    SeedAppointment(f"{PREFIX}RAMESH", "Dialysis station 3", 4, time(8, 0)),
    SeedAppointment(f"{PREFIX}FATIMA", "Echo cardiologist", 2, time(15, 0)),
)


class Seeder:
    """Looks before it writes, and says everything it does."""

    def __init__(self, client: httpx.Client, *, write: bool, timezone: str) -> None:
        self.client = client
        self.write = write
        self.timezone = timezone
        self.did: list[str] = []
        self.would: list[str] = []

    # ---------------- plumbing ----------------

    def get(self, path: str, **params) -> object:
        response = self.client.get(path, params=params or None)
        response.raise_for_status()
        return response.json() if response.content else None

    def post(self, path: str, payload: dict) -> object:
        response = self.client.post(path, json=payload)
        response.raise_for_status()
        return response.json() if response.content else None

    def _note(self, message: str) -> None:
        (self.did if self.write else self.would).append(message)
        logger.info("%s %s", "did:" if self.write else "would:", message)

    # ---------------- services ----------------

    def existing_services(self) -> dict[str, str]:
        rows = self.get("/openmrs/ws/rest/v1/appointmentService/all/full") or []
        return {
            str(r.get("name", "")).strip(): str(r.get("uuid", ""))
            for r in rows
            if isinstance(r, dict)
        }

    def ensure_services(self) -> dict[str, str]:
        known = self.existing_services()
        for service in SERVICES:
            if service.name in known:
                logger.info("service %r already exists", service.name)
                continue
            self._note(f"create appointment service {service.name!r}")
            if not self.write:
                known[service.name] = f"<would-create:{service.name}>"
                continue
            made = self.post(
                "/openmrs/ws/rest/v1/appointmentService",
                {
                    "name": service.name,
                    "description": f"{service.name} (EKYATRA demo)",
                    "durationMins": service.duration_minutes,
                },
            )
            known[service.name] = str((made or {}).get("uuid", ""))
        return known

    # ---------------- patients ----------------

    def _identifier_type(self) -> str:
        rows = (self.get("/openmrs/ws/rest/v1/patientidentifiertype") or {}).get("results", [])
        for row in rows:
            if row.get("name") == "Patient Identifier":
                return str(row["uuid"])
        if not rows:
            raise RuntimeError("this Bahmni has no patient identifier types")
        return str(rows[0]["uuid"])

    def _registration_location(self) -> str:
        rows = (
            self.get("/openmrs/ws/rest/v1/location", tag="Login Location") or {}
        ).get("results", [])
        for row in rows:
            if "registration" in str(row.get("display", row.get("name", ""))).lower():
                return str(row["uuid"])
        if not rows:
            raise RuntimeError("this Bahmni has no login locations")
        return str(rows[0]["uuid"])

    def find_patient(self, identifier: str) -> str | None:
        found = (
            self.get("/openmrs/ws/rest/v1/patient", q=identifier, v="custom:(uuid,display)")
            or {}
        ).get("results", [])
        for row in found:
            if identifier.lower() in str(row.get("display", "")).lower():
                return str(row["uuid"])
        return None

    def ensure_patients(self) -> dict[str, str]:
        refs: dict[str, str] = {}
        identifier_type = ""
        location = ""
        for patient in PATIENTS:
            standing = self.find_patient(patient.identifier)
            if standing:
                logger.info("patient %s already exists", patient.identifier)
                refs[patient.identifier] = standing
                continue
            self._note(f"register patient {patient.identifier} ({patient.given_name})")
            if not self.write:
                refs[patient.identifier] = f"<would-create:{patient.identifier}>"
                continue
            identifier_type = identifier_type or self._identifier_type()
            location = location or self._registration_location()
            made = self.post(
                "/openmrs/ws/rest/v1/patient",
                {
                    "person": {
                        "names": [
                            {
                                "givenName": patient.given_name,
                                "familyName": patient.family_name,
                            }
                        ],
                        "gender": patient.gender,
                        "birthdate": patient.birthdate,
                        "addresses": [{"cityVillage": patient.village}],
                    },
                    "identifiers": [
                        {
                            "identifier": patient.identifier,
                            "identifierType": identifier_type,
                            "location": location,
                            "preferred": True,
                        }
                    ],
                },
            )
            refs[patient.identifier] = str((made or {}).get("uuid", ""))
        return refs

    # ---------------- appointments ----------------

    def ensure_appointments(
        self, services: dict[str, str], patients: dict[str, str], today: date
    ) -> dict[tuple[str, str], date]:
        """Book what is missing, and report the day each booking actually sits on.

        The return value is why this is not a plain `None`. Our own records and
        Bahmni's must agree on dates, and computing both from "today" makes
        them agree only if both halves are seeded on the same day. They were
        not — Bahmni was re-seeded two days after the local cast, every
        appointment moved two days, and a cancellation then landed on a date
        no local step was sitting on, so a real disruption affected nobody.

        So Bahmni is the single source of truth for when things happen, and
        the local cast is written from what this returns.
        """
        booked: dict[tuple[str, str], date] = {}
        window_start = today - timedelta(days=1)
        window_end = today + timedelta(days=14)
        standing = self.post(
            "/openmrs/ws/rest/v1/appointments/search",
            {
                "startDate": _instant(datetime.combine(window_start, time.min, tzinfo=UTC)),
                "endDate": _instant(datetime.combine(window_end, time.max, tzinfo=UTC)),
            },
        )
        for row in (standing or []):
            if not isinstance(row, dict) or row.get("voided"):
                continue
            identifier = str((row.get("patient") or {}).get("identifier", ""))
            service = str((row.get("service") or {}).get("name", ""))
            at = row.get("startDateTime")
            if identifier.startswith(PREFIX) and service and at:
                booked.setdefault(
                    (identifier, service),
                    datetime.fromtimestamp(at / 1000, tz=UTC).date(),
                )

        # Only *open* appointments count as already held. A cancelled one is
        # exactly what this script exists to undo: the demo's start state is
        # that Kamla has a scheduled MRI, and after a run (or a judge) has
        # cancelled it, re-seeding has to put a real one back. Counting a
        # cancelled slot as "already exists" made the reset silently do
        # nothing, which is the one thing a reset must never do.
        held = {
            (
                str((row.get("patient") or {}).get("identifier", "")),
                str((row.get("service") or {}).get("name", "")),
                int(row.get("startDateTime") or 0),
            )
            for row in (standing or [])
            if isinstance(row, dict)
            and not row.get("voided")
            and str(row.get("status", "")).strip().lower()
            not in ("cancelled", "canceled", "missed")
        }

        for booking in APPOINTMENTS:
            day = today + timedelta(days=booking.days_from_today)
            starts_at = datetime.combine(day, booking.at, tzinfo=UTC)
            key = (
                booking.patient_identifier,
                booking.service_name,
                int(starts_at.timestamp() * 1000),
            )
            booked[(booking.patient_identifier, booking.service_name)] = day
            if key in held:
                logger.info(
                    "appointment for %s on %s already exists",
                    booking.patient_identifier,
                    day.isoformat(),
                )
                continue

            duration = next(
                (s.duration_minutes for s in SERVICES if s.name == booking.service_name), 30
            )
            self._note(
                f"book {booking.service_name} for {booking.patient_identifier} "
                f"on {day:%a %d %b} at {booking.at:%H:%M}"
            )
            if not self.write:
                continue
            self.post(
                "/openmrs/ws/rest/v1/appointments",
                {
                    "patientUuid": patients[booking.patient_identifier],
                    "serviceUuid": services[booking.service_name],
                    "startDateTime": _instant(starts_at),
                    "endDateTime": _instant(starts_at + timedelta(minutes=duration)),
                    "appointmentKind": "Scheduled",
                    "providers": [],
                    "comments": "EKYATRA demo seed",
                },
            )
        return booked

    def run(self, today: date) -> dict[tuple[str, str], date]:
        services = self.ensure_services()
        patients = self.ensure_patients()
        return self.ensure_appointments(services, patients, today)


def _instant(moment: datetime) -> str:
    aware = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    return aware.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ---------------- our own side of the same cast ----------------


#: Which of our resources each Bahmni service books, so a re-align knows which
#: step a given appointment is the booking for.
_SERVICE_OF_RESOURCE = {
    "EKY-MRI-1": "MRI machine 1",
    "EKY-MRI-2": "MRI machine 2",
    "EKY-ECHO": "Echo cardiologist",
    "EKY-DIALYSIS-3": "Dialysis station 3",
}


def _realign(store, booked: dict, when) -> bool:
    """Move existing local steps onto the dates the hospital actually holds.

    Shared with the OpenEMR seeder, which is why nothing here names Bahmni:
    the drift it repairs is a property of seeding two systems on different
    days, not of any one of them.

    Returns True when anything moved. Only touches steps that are still
    waiting to happen and that name one of the seeded resources — a completed
    step is history, and a step belonging to a real family is none of this
    script's business.
    """
    from ..domain.enums import StepStatus

    records = store.load()
    moved = 0
    for patient in records.patients:
        if not patient.id.startswith(PREFIX):
            continue
        for step in records.steps.get(patient.id, ()):
            service = _SERVICE_OF_RESOURCE.get(step.resource_id or "")
            if not service or step.status is not StepStatus.SCHEDULED:
                continue
            wanted = booked.get((patient.id, service))
            if wanted is None or step.scheduled_for == wanted:
                continue
            store.save_step(step.model_copy(update={"scheduled_for": wanted}))
            logger.info(
                "re-aligned %s from %s to %s, where the hospital holds it",
                step.id,
                step.scheduled_for,
                wanted,
            )
            moved += 1
    if not moved:
        logger.info("the local cast is already in place and agrees with the hospital")
    return bool(moved)


def _abha_for(identifier: str) -> str:
    """A stable, obviously-fake ABHA number for a demo family.

    The 14-digit shape ABDM uses, always starting 99 — a prefix the authority
    does not issue, so one of these can never collide with a real person's
    health id however far this database travels. Derived from the patient id
    so it is the same on every reseed, which matters because a consent grant
    recorded yesterday has to still match tomorrow.
    """
    # sha256, not `hash()`: Python salts the built-in per process, so a
    # reseed tomorrow would mint a different number and orphan every consent
    # grant recorded today — the precise failure this docstring promises not
    # to have. Checked, and it did exactly that before this line changed.
    digest = hashlib.sha256(identifier.encode()).hexdigest()
    return f"99{int(digest, 16) % 10**12:012d}"


def seed_local_cast(
    store,
    today: date,
    *,
    hospital_id: str,
    district_id: str = "GAYA-DH",
    booked: dict[tuple[str, str], date] | None = None,
) -> bool:
    """Write the same four families into our records, so the two sides match.

    Seeding Bahmni alone proves nothing: the connector matches an appointment
    to a family by **identifier** and to a machine by **service name**, so
    until our records hold a patient whose id is `EKY-KAMLA` and a resource
    whose display name is `MRI machine 1`, a cancellation in Bahmni is just
    somebody else's patient and correctly changes nothing here.

    So this is the other half of the seed, and the two halves must be edited
    together. Idempotent like the rest: an existing `EKY-` family means the
    cast is already in place and nothing is written.

    **Two hospitals, because the journey is.** Kamla is treated in Mumbai but
    her creatinine is done at her district hospital in Gaya — nobody travels
    a thousand kilometres for a blood test. So her bloods carry a Gaya
    resource and her scan a Mumbai one, which is what makes her Mumbai
    appointment depend on a result that Mumbai's own system cannot see.

    Logistics only, as everywhere else: a status, a date, a queue. Nothing here
    says what anyone has or what any report found.
    """
    from ..domain.enums import (
        Language,
        ResourceKind,
        StepKind,
        StepStatus,
    )
    from ..domain.models import CareStep, Patient, Resource

    booked = booked or {}

    def when(patient_identifier: str, service: str, fallback_days: int) -> date:
        """The day Bahmni actually holds this, not the day we would have picked."""
        return booked.get((patient_identifier, service), today + timedelta(days=fallback_days))

    if any(p.id.startswith(PREFIX) for p in store.load().patients):
        # Already here — but the dates may have drifted if Bahmni was re-seeded
        # on a different day, and a drifted date is worse than no date: a real
        # cancellation lands on a day no step is sitting on and silently
        # affects nobody. Re-align and say so.
        return _realign(store, booked, when)

    # Display names are the join key to Bahmni's appointment services. They are
    # not labels — changing one here silently unlinks a machine.
    for resource in (
        Resource(id="EKY-MRI-1", kind=ResourceKind.MACHINE, display_name="MRI machine 1",
                 hospital_id=hospital_id, department="scan"),
        Resource(id="EKY-MRI-2", kind=ResourceKind.MACHINE, display_name="MRI machine 2",
                 hospital_id=hospital_id, department="scan"),
        Resource(id="EKY-ECHO", kind=ResourceKind.STAFF, display_name="Echo cardiologist",
                 hospital_id=hospital_id, department="echo_review"),
        Resource(id="EKY-DIALYSIS-3", kind=ResourceKind.MACHINE,
                 display_name="Dialysis station 3", hospital_id=hospital_id,
                 department="dialysis_session"),
        # The other hospital. Its lab is where the creatinine actually happens,
        # and its id is what makes `GAYA-DH` appear on the panel at all.
        Resource(id="EKY-GAYA-LAB", kind=ResourceKind.SUPPLY,
                 display_name="District lab", hospital_id=district_id,
                 department="bloods"),
    ):
        store.save_resource(resource)

    earlier = today - timedelta(days=6)

    def family(
        identifier: str,
        name: str,
        district: str,
        km: float,
        pathway: str,
        target: StepKind | None = None,
    ) -> None:
        """One family, and the visit their journey is currently planned around.

        The target matters more than it looks. Left unset, an oncology family
        is planned towards `review_consult` — which depends on a radiology
        report, which cannot be forecast until the scan has actually happened.
        The planner then answers UNCERTAIN, correctly and uselessly: it is
        being asked when a visit two steps away will be possible.

        The visit these families are actually travelling for is the one in the
        hospital's diary. So that is what each is planned towards, and it is
        the appointment a cancellation takes away.
        """
        store.save_patient(
            Patient(
                id=identifier,
                name=name,
                home_district=district,
                home_distance_km=km,
                language=Language.HINDI,
                caregiver_phone="",
                # A made-up ABHA number in the 14-digit shape ABDM uses, in
                # the 99 range that is not issued to anybody. Without one
                # these families cannot be matched to a consent grant at all
                # — consent is keyed on ABHA, as ABDM requires — so the
                # research export silently excluded every one of them and
                # reported "no consent" for a cohort that had never been
                # asked. A demo cast with no health id is not a demo cast.
                abha_number=_abha_for(identifier),
                hospital_id=hospital_id,
                pathway_id=pathway,
            ),
            target,
        )

    def step(pid, kind, status, *, on=None, resource=None, released=None) -> None:
        store.save_step(
            CareStep(
                id=f"{pid}-{kind.value}",
                patient_id=pid,
                kind=kind,
                status=status,
                scheduled_for=on,
                # `step_problem` refuses a completed step with no date and a
                # pending report with no queue; either makes the planner answer
                # UNCERTAIN for ever rather than loudly.
                completed_on=earlier if status is StepStatus.COMPLETED else None,
                result_available_on=released,
                queue=kind.value,
                resource_id=resource,
            )
        )

    # Kamla is the story: everything before the scan is done, so the scan is
    # the only thing standing between her and a date — which is what makes
    # cancelling it in Bahmni land on her and nobody else.
    def oncology_spine(pid: str, *, bloods_at: str | None = None) -> None:
        """Everything the review consult leans on, in the state it would be in.

        The pathway makes `review_consult` depend on the pathology report, the
        radiology report and the bloods — and the radiology report in turn on
        the scan. Seeding a family without the full chain does not produce a
        half-plan; it produces "plan could not be determined", the family drops
        to UNCERTAIN and a real cancellation yields no options at all. The
        record has to be coherent before any of this is worth watching.
        """
        for kind in (StepKind.CONSULT, StepKind.BIOPSY):
            step(pid, kind, StepStatus.COMPLETED)
        step(pid, StepKind.BLOODS, StepStatus.COMPLETED, resource=bloods_at)
        step(pid, StepKind.PATHOLOGY_REPORT, StepStatus.RESULT_AVAILABLE, released=earlier)
        # Not yet: it follows the scan, and the scan has not happened. This is
        # the step that makes the scan matter to the review consult, which is
        # what makes cancelling the scan worth re-planning around.
        step(pid, StepKind.RADIOLOGY_REPORT, StepStatus.NOT_SCHEDULED)
        step(pid, StepKind.REVIEW_CONSULT, StepStatus.NOT_SCHEDULED)

    family(f"{PREFIX}KAMLA", "Kamla Devi", "Gaya", 1020.0, "oncology", StepKind.SCAN)
    # Her bloods are done at the district hospital, not in Mumbai — nobody
    # travels a thousand kilometres for a blood test. That is what puts her
    # journey across two hospitals whose systems cannot see each other.
    oncology_spine(f"{PREFIX}KAMLA", bloods_at="EKY-GAYA-LAB")
    step(f"{PREFIX}KAMLA", StepKind.SCAN, StepStatus.SCHEDULED,
         on=when(f"{PREFIX}KAMLA", "MRI machine 1", 3), resource="EKY-MRI-1")

    family(f"{PREFIX}SHANTI", "Shanti Kumari", "Darbhanga", 820.0, "oncology", StepKind.SCAN)
    oncology_spine(f"{PREFIX}SHANTI")
    step(f"{PREFIX}SHANTI", StepKind.SCAN, StepStatus.SCHEDULED,
         on=when(f"{PREFIX}SHANTI", "MRI machine 2", 3), resource="EKY-MRI-2")

    family(
        f"{PREFIX}RAMESH", "Ramesh Prasad", "Patna", 610.0, "dialysis",
        StepKind.DIALYSIS_SESSION,
    )
    step(f"{PREFIX}RAMESH", StepKind.BLOODS, StepStatus.COMPLETED)
    step(f"{PREFIX}RAMESH", StepKind.NEPHROLOGY_REVIEW, StepStatus.COMPLETED)
    step(f"{PREFIX}RAMESH", StepKind.DIALYSIS_SESSION, StepStatus.SCHEDULED,
         on=when(f"{PREFIX}RAMESH", "Dialysis station 3", 1), resource="EKY-DIALYSIS-3")

    family(f"{PREFIX}FATIMA", "Fatima Begum", "Samastipur", 740.0, "oncology", StepKind.ECHO_REVIEW)
    oncology_spine(f"{PREFIX}FATIMA")
    step(f"{PREFIX}FATIMA", StepKind.SCAN, StepStatus.COMPLETED)
    step(f"{PREFIX}FATIMA", StepKind.ECHO_REVIEW, StepStatus.SCHEDULED,
         on=when(f"{PREFIX}FATIMA", "Echo cardiologist", 2), resource="EKY-ECHO")

    _seed_turnaround(store, today, hospital_id)
    logger.info("wrote %d families into our own records", len(PATIENTS))
    return True


#: Report queues the seeded families wait on, and how long each has historically
#: taken. Plausible rather than invented: a radiology report back in two to four
#: days, pathology in four to seven.
_HISTORY: dict[str, tuple[float, ...]] = {
    "radiology_report": (2.0, 3.0, 2.0, 4.0, 3.0, 2.0, 3.0, 3.0, 2.0, 4.0, 3.0, 2.0),
    "pathology_report": (5.0, 6.0, 4.0, 7.0, 5.0, 5.0, 6.0, 4.0, 5.0, 6.0, 5.0, 7.0),
}


def _seed_turnaround(store, today: date, hospital_id: str) -> None:
    """Give the forecast something to have learned from.

    Without this the conformal predictor has no calibration set, every report
    window comes back `None`, and the planner answers UNCERTAIN for every
    family — correctly, because a system that has never seen this queue
    release a report genuinely does not know when the next one lands. That is
    the right answer and a useless demonstration, so the seed supplies the
    history a hospital running for a month would already have.

    `MIN_CALIBRATION` is 10, so there are twelve of each: enough to be
    calibrated, few enough that one unusual week would still move it.
    """
    from ..ports.records import TurnaroundObservation

    for queue, days in _HISTORY.items():
        for number, taken in enumerate(days):
            store.add_turnaround(
                TurnaroundObservation(
                    queue=queue,
                    days=taken,
                    observed_on=today - timedelta(days=1 + number * 3),
                    hospital_id=hospital_id,
                )
            )


def _report(seeder: Seeder, base_url: str, today: date) -> int:
    """What this Bahmni holds right now. Reads only; changes nothing."""
    services = seeder.existing_services()
    print(f"\nBahmni at {base_url}")
    print(f"  {len(services)} appointment service(s)")
    for name in sorted(services):
        print(f"    - {name}")

    rows = seeder.post(
        "/openmrs/ws/rest/v1/appointments/search",
        {
            "startDate": _instant(
                datetime.combine(today - timedelta(days=30), time.min, tzinfo=UTC)
            ),
            "endDate": _instant(
                datetime.combine(today + timedelta(days=30), time.max, tzinfo=UTC)
            ),
        },
    ) or []
    print(f"  {len(rows)} appointment(s) in a 60-day window")
    for row in rows[:20]:
        patient = (row.get("patient") or {}).get("identifier", "?")
        service = (row.get("service") or {}).get("name", "?")
        print(f"    - {row.get('status', '?'):10} {service:34} {patient}")

    missing = [s.name for s in SERVICES if s.name not in services]
    if missing:
        print(f"\n  The demo still needs: {', '.join(missing)}")
        print("  Run `make bahmni-seed` to see what would be created.")
    return 0


def _seed_local(settings, today: date, booked: dict) -> None:
    """Write our half of the cast, through the same store a desk writes to."""
    from ..adapters.records import SqlRecordStore

    store = SqlRecordStore(settings.records_url)
    hospital_id = (settings.hospital_places[0].split("=")[0]
                   if settings.hospital_places else "TMH-MUM")
    if seed_local_cast(store, today, hospital_id=hospital_id, booked=booked):
        print(f"  wrote the matching cast into {settings.records_url}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="actually create things. Without it, nothing is written anywhere.",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help=(
            "also write the matching families into our own records "
            "(needs SAATHI_WORLD=real). Without this the Bahmni side has a "
            "cast and our side does not, so nothing a judge cancels matches."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="just report what this Bahmni holds, and stop.",
    )
    parser.add_argument("--base-url", default=None, help="overrides SAATHI_BAHMNI_BASE_URL")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = get_settings()
    base_url = (args.base_url or settings.bahmni_base_url or "").rstrip("/")
    if not (base_url and settings.bahmni_username and settings.bahmni_password):
        print(
            "No Bahmni configured. Set SAATHI_BAHMNI_BASE_URL, _USERNAME and _PASSWORD.",
            file=sys.stderr,
        )
        return 2

    today = date.today()
    with httpx.Client(
        base_url=base_url,
        auth=(settings.bahmni_username, settings.bahmni_password),
        timeout=30.0,
        headers={"Accept": "application/json"},
    ) as client:
        seeder = Seeder(client, write=args.write, timezone=settings.hospital_timezone)
        try:
            if args.check:
                return _report(seeder, base_url, today)
            booked = seeder.run(today)
            if args.local:
                _seed_local(settings, today, booked)
        except httpx.HTTPStatusError as exc:
            print(
                f"\nBahmni refused: {exc.response.status_code} {exc.response.text[:300]}",
                file=sys.stderr,
            )
            return 1

    if args.write:
        print(f"\nDone. {len(seeder.did)} change(s) made to {base_url}.")
    else:
        print(f"\nDry run against {base_url}. {len(seeder.would)} change(s) would be made:")
        for line in seeder.would:
            print(f"  - {line}")
        print("\nNothing was written. Re-run with --write to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
