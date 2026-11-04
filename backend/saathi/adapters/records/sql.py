"""A record store over SQLAlchemy.

Synchronous on purpose: the world is a plain in-memory object that planning
reads from worker threads, and each write here is one small transaction. The
URL decides the database, so SQLite today and Postgres later is a config
change; `migrate()` brings the schema to the current revision on either.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from ...db.tables import (
    AccessAttemptRow,
    ApprovalRow,
    CareStepRow,
    ConsentGrantRow,
    ConsentRequestRow,
    DisruptionRow,
    FamilyMemberRow,
    FamilyMessageRow,
    OptionSetRow,
    PatientRow,
    ReadinessItemRow,
    RecordPointerRow,
    ResourceRow,
    TurnaroundRow,
)
from ...domain.consent import AccessAttempt, ConsentGrant, ConsentRequest, RecordPointer
from ...domain.enums import (
    Channel,
    FamilyMemberRole,
    Language,
    ResourceKind,
    StepKind,
    StepStatus,
)
from ...domain.models import (
    ApprovalDecision,
    CareStep,
    Disruption,
    FamilyMember,
    Patient,
    PlanOption,
    ReadinessItem,
    Resource,
)
from ...ports.records import StoredOptionSet, StoredRecords, TurnaroundObservation

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
            disruptions = tuple(
                Disruption.model_validate_json(r.payload_json)
                for r in db.scalars(select(DisruptionRow).order_by(DisruptionRow.id))
            )
            readiness = tuple(
                ReadinessItem.model_validate_json(r.payload_json)
                for r in db.scalars(
                    select(ReadinessItemRow).order_by(
                        ReadinessItemRow.patient_id, ReadinessItemRow.item_id
                    )
                )
            )
            option_sets = tuple(
                StoredOptionSet(
                    patient_id=r.patient_id,
                    disruption_id=r.disruption_id,
                    options=tuple(
                        PlanOption.model_validate(o) for o in json.loads(r.payload_json)
                    ),
                    created_at=_aware(r.created_at),
                )
                for r in db.scalars(select(OptionSetRow).order_by(OptionSetRow.created_at))
            )
            approvals = tuple(
                ApprovalDecision.model_validate_json(r.payload_json)
                for r in db.scalars(select(ApprovalRow).order_by(ApprovalRow.approved_at))
            )
            consent_requests = tuple(
                ConsentRequest.model_validate_json(r.payload_json)
                for r in db.scalars(select(ConsentRequestRow).order_by(ConsentRequestRow.id))
            )
            consent_grants = tuple(
                ConsentGrant.model_validate_json(r.payload_json)
                for r in db.scalars(select(ConsentGrantRow).order_by(ConsentGrantRow.id))
            )
            pointers = tuple(
                RecordPointer.model_validate_json(r.payload_json)
                for r in db.scalars(select(RecordPointerRow).order_by(RecordPointerRow.id))
            )
            attempts = tuple(
                AccessAttempt.model_validate_json(r.payload_json)
                for r in db.scalars(select(AccessAttemptRow).order_by(AccessAttemptRow.at))
            )
            family_messages = tuple(
                json.loads(r.payload_json)
                for r in db.scalars(select(FamilyMessageRow).order_by(FamilyMessageRow.sent_at))
            )
        return StoredRecords(
            patients=tuple(patients),
            steps={pid: tuple(rows) for pid, rows in steps.items()},
            resources=resources,
            plan_targets=targets,
            turnaround=turnaround,
            disruptions=disruptions,
            readiness_items=readiness,
            option_sets=option_sets,
            approvals=approvals,
            family_messages=family_messages,
            consent_requests=consent_requests,
            consent_grants=consent_grants,
            record_pointers=pointers,
            access_attempts=attempts,
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
            row.caregiver_email = patient.caregiver_email
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

    def save_disruption(self, disruption: Disruption) -> None:
        with self._sessions.begin() as db:
            row = db.get(DisruptionRow, disruption.id)
            if row is None:
                row = DisruptionRow(id=disruption.id)
                db.add(row)
            row.resource_id = disruption.resource_id
            row.unavailable_to = disruption.unavailable_to
            row.payload_json = disruption.model_dump_json()

    def save_readiness_item(self, item: ReadinessItem) -> None:
        with self._sessions.begin() as db:
            row = db.get(ReadinessItemRow, (item.patient_id, item.id))
            if row is None:
                row = ReadinessItemRow(patient_id=item.patient_id, item_id=item.id)
                db.add(row)
            row.payload_json = item.model_dump_json()

    def delete_readiness_item(self, patient_id: str, item_id: str) -> None:
        with self._sessions.begin() as db:
            row = db.get(ReadinessItemRow, (patient_id, item_id))
            if row is not None:
                db.delete(row)

    def save_option_set(self, option_set: StoredOptionSet) -> None:
        with self._sessions.begin() as db:
            row = db.get(OptionSetRow, option_set.patient_id)
            if row is None:
                row = OptionSetRow(patient_id=option_set.patient_id)
                db.add(row)
            row.disruption_id = option_set.disruption_id
            row.created_at = option_set.created_at
            row.payload_json = json.dumps([o.model_dump(mode="json") for o in option_set.options])

    def delete_option_set(self, patient_id: str) -> None:
        with self._sessions.begin() as db:
            row = db.get(OptionSetRow, patient_id)
            if row is not None:
                db.delete(row)

    def add_family_message(self, row: dict) -> None:
        with self._sessions.begin() as db:
            if db.get(FamilyMessageRow, row["id"]) is not None:
                return  # a message already on file is never rewritten
            db.add(
                FamilyMessageRow(
                    id=row["id"],
                    patient_id=row["patient_id"],
                    sent_at=datetime.fromisoformat(row["sent_at"]),
                    payload_json=json.dumps(row),
                )
            )

    def add_approval(self, approval: ApprovalDecision) -> None:
        with self._sessions.begin() as db:
            if db.get(ApprovalRow, approval.id) is not None:
                return  # append-only: an approval already on file is never rewritten
            db.add(
                ApprovalRow(
                    id=approval.id,
                    patient_id=approval.patient_id,
                    disruption_id=approval.disruption_id,
                    approved_at=approval.approved_at,
                    payload_json=approval.model_dump_json(),
                )
            )

    def save_consent_request(self, request: ConsentRequest) -> None:
        self._upsert(ConsentRequestRow, request.id, request.abha_number, request)

    def save_consent_grant(self, grant: ConsentGrant) -> None:
        self._upsert(ConsentGrantRow, grant.id, grant.abha_number, grant)

    def save_record_pointer(self, pointer: RecordPointer) -> None:
        self._upsert(RecordPointerRow, pointer.id, pointer.abha_number, pointer)

    def add_access_attempt(self, attempt: AccessAttempt) -> None:
        with self._sessions.begin() as db:
            if db.get(AccessAttemptRow, attempt.id) is not None:
                return  # append-only: an attempt already on file is never rewritten
            db.add(
                AccessAttemptRow(
                    id=attempt.id,
                    abha_number=attempt.abha_number,
                    at=attempt.at,
                    payload_json=attempt.model_dump_json(),
                )
            )

    def _upsert(self, table, key: str, abha_number: str, model) -> None:
        with self._sessions.begin() as db:
            row = db.get(table, key)
            if row is None:
                row = table(id=key)
                db.add(row)
            row.abha_number = abha_number
            row.payload_json = model.model_dump_json()


def _aware(moment: datetime) -> datetime:
    """SQLite drops the timezone it was given; everything here is UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _patient(row: PatientRow) -> Patient:
    return Patient(
        id=row.id,
        name=row.name or "",
        abha_number=row.abha_number,
        home_district=row.home_district,
        home_distance_km=row.home_distance_km,
        language=Language(row.language),
        caregiver_phone=row.caregiver_phone,
        caregiver_email=row.caregiver_email,
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
