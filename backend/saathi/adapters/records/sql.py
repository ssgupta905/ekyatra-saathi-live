"""A record store over SQLAlchemy.

Synchronous on purpose: the world is a plain in-memory object that planning
reads from worker threads, and each write here is one small transaction. The
URL decides the database, so SQLite today and Postgres later is a config
change; `migrate()` brings the schema to the current revision on either.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from ...db.tables import (
    CareStepRow,
    FamilyMemberRow,
    PatientRow,
    ResourceRow,
    TurnaroundRow,
)
from ...domain.enums import (
    Channel,
    FamilyMemberRole,
    Language,
    ResourceKind,
    StepKind,
    StepStatus,
)
from ...domain.models import CareStep, FamilyMember, Patient, Resource
from ...ports.records import StoredRecords, TurnaroundObservation

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"


def migrate(url: str, revision: str = "head") -> None:
    """Bring the database at `url` to `revision` (default: current)."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, revision)


class SqlRecordStore:
    def __init__(self, url: str, *, migrate_on_open: bool = True) -> None:
        if migrate_on_open:
            migrate(url)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self._engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)

    def close(self) -> None:
        self._engine.dispose()

    # ---------------- reading ----------------

    def load(self) -> StoredRecords:
        with self._sessions() as db:
            patients: list[Patient] = []
            targets: dict[str, StepKind] = {}
            for row in db.scalars(select(PatientRow).order_by(PatientRow.id)):
                patients.append(_patient(row))
                if row.plan_target_kind:
                    targets[row.id] = StepKind(row.plan_target_kind)

            steps: dict[str, list[CareStep]] = {p.id: [] for p in patients}
            for row in db.scalars(select(CareStepRow).order_by(CareStepRow.id)):
                steps.setdefault(row.patient_id, []).append(_step(row))

            resources = tuple(_resource(r) for r in db.scalars(select(ResourceRow)))
            turnaround = tuple(
                TurnaroundObservation(
                    queue=r.queue,
                    days=r.days,
                    observed_on=r.observed_on,
                    hospital_id=r.hospital_id,
                )
                for r in db.scalars(select(TurnaroundRow).order_by(TurnaroundRow.id))
            )
        return StoredRecords(
            patients=tuple(patients),
            steps={pid: tuple(rows) for pid, rows in steps.items()},
            resources=resources,
            plan_targets=targets,
            turnaround=turnaround,
        )

    # ---------------- writing ----------------

    def save_patient(self, patient: Patient, plan_target: StepKind | None = None) -> None:
        with self._sessions.begin() as db:
            row = db.get(PatientRow, patient.id)
            if row is None:
                row = PatientRow(id=patient.id)
                db.add(row)
            row.name = patient.name
            row.abha_number = patient.abha_number
            row.home_district = patient.home_district
            row.home_distance_km = patient.home_distance_km
            row.language = patient.language.value
            row.caregiver_phone = patient.caregiver_phone
            row.hospital_id = patient.hospital_id
            row.pathway_id = patient.pathway_id
            if plan_target is not None:
                row.plan_target_kind = plan_target.value

            wanted = {m.id: m for m in patient.family_members}
            existing = {m.id: m for m in row.family}
            for member_id, member in wanted.items():
                member_row = existing.get(member_id) or FamilyMemberRow(
                    id=member_id, patient_id=patient.id
                )
                member_row.role = member.role.value
                member_row.name = member.name
                member_row.phone = member.phone
                member_row.preferred_channel = member.preferred_channel.value
                member_row.language = member.language.value
                if member_id not in existing:
                    db.add(member_row)
            for member_id, member_row in existing.items():
                if member_id not in wanted:
                    db.delete(member_row)

    def save_step(self, step: CareStep) -> None:
        with self._sessions.begin() as db:
            row = db.get(CareStepRow, step.id)
            if row is None:
                row = CareStepRow(id=step.id, patient_id=step.patient_id)
                db.add(row)
            row.kind = step.kind.value
            row.status = step.status.value
            row.scheduled_for = step.scheduled_for
            row.completed_on = step.completed_on
            row.result_available_on = step.result_available_on
            row.queue = step.queue
            row.resource_id = step.resource_id

    def save_resource(self, resource: Resource) -> None:
        with self._sessions.begin() as db:
            row = db.get(ResourceRow, resource.id)
            if row is None:
                row = ResourceRow(id=resource.id)
                db.add(row)
            row.kind = resource.kind.value
            row.display_name = resource.display_name
            row.hospital_id = resource.hospital_id
            row.department = resource.department

    def add_turnaround(self, observation: TurnaroundObservation) -> None:
        with self._sessions.begin() as db:
            db.add(
                TurnaroundRow(
                    hospital_id=observation.hospital_id,
                    queue=observation.queue,
                    days=observation.days,
                    observed_on=observation.observed_on,
                )
            )


def _patient(row: PatientRow) -> Patient:
    return Patient(
        id=row.id,
        name=row.name or "",
        abha_number=row.abha_number,
        home_district=row.home_district,
        home_distance_km=row.home_distance_km,
        language=Language(row.language),
        caregiver_phone=row.caregiver_phone,
        hospital_id=row.hospital_id,
        pathway_id=row.pathway_id or "oncology",
        family_members=tuple(
            FamilyMember(
                id=m.id,
                patient_id=m.patient_id,
                role=FamilyMemberRole(m.role),
                name=m.name,
                phone=m.phone,
                preferred_channel=Channel(m.preferred_channel),
                language=Language(m.language),
            )
            for m in sorted(row.family, key=lambda m: m.id)
        ),
    )


def _step(row: CareStepRow) -> CareStep:
    return CareStep(
        id=row.id,
        patient_id=row.patient_id,
        kind=StepKind(row.kind),
        status=StepStatus(row.status),
        scheduled_for=row.scheduled_for,
        completed_on=row.completed_on,
        result_available_on=row.result_available_on,
        queue=row.queue,
        resource_id=row.resource_id,
    )


def _resource(row: ResourceRow) -> Resource:
    return Resource(
        id=row.id,
        kind=ResourceKind(row.kind),
        display_name=row.display_name,
        hospital_id=row.hospital_id,
        department=row.department,
    )
