"""Persistence schema.

The in-memory ledger and cohort are what the prototype runs on; these tables are
what the pilot writes to. The shapes mirror the domain models deliberately, so
the mapping stays boring.

Note what is absent: there is no column anywhere that can hold report content.
The schema itself enforces the project's scope boundary.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PatientRow(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    abha_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    #: The step kind this family is planned towards; null means the pathway's
    #: terminal visit (a review consult).
    plan_target_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    home_district: Mapped[str] = mapped_column(String(128))
    home_distance_km: Mapped[float] = mapped_column(Float)
    language: Mapped[str] = mapped_column(String(8))
    caregiver_phone: Mapped[str] = mapped_column(String(24))
    caregiver_email: Mapped[str | None] = mapped_column(String(254), nullable=True, index=True)
    hospital_id: Mapped[str] = mapped_column(String(32), index=True)
    pathway_id: Mapped[str] = mapped_column(
        String(32), default="oncology", server_default="oncology"
    )

    steps: Mapped[list[CareStepRow]] = relationship(back_populates="patient")
    family: Mapped[list[FamilyMemberRow]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )


class FamilyMemberRow(Base):
    __tablename__ = "family_members"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(24))
    preferred_channel: Mapped[str] = mapped_column(String(16))
    language: Mapped[str] = mapped_column(String(8))

    patient: Mapped[PatientRow] = relationship(back_populates="family")


class UserRow(Base):
    """A staff account. Families have none: they prove a phone number instead."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class HospitalRow(Base):
    __tablename__ = "hospitals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    place: Mapped[str] = mapped_column(String(80))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    departments_json: Mapped[str] = mapped_column(Text, default="[]")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class CentreRow(Base):
    __tablename__ = "centres"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hospital_id: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(160))
    place: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(16), default="day_care")
    handles_json: Mapped[str] = mapped_column(Text, default="[]")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ClinicianRow(Base):
    __tablename__ = "clinicians"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    specialty: Mapped[str] = mapped_column(String(120), default="")
    hospital_id: Mapped[str] = mapped_column(String(32), index=True)
    department: Mapped[str] = mapped_column(String(80), default="")
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class OrganisationRow(Base):
    """A lab, pharmacy, distributor, cab service, hotel or other party in the network."""

    __tablename__ = "organisations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    type: Mapped[str] = mapped_column(String(32), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="simulated")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    payload_json: Mapped[str] = mapped_column(Text)


class FamilyProfileRow(Base):
    """What a family told us when they were taken on, section by section."""

    __tablename__ = "family_profiles"

    patient_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    sections_json: Mapped[str] = mapped_column(Text, default="{}")
    activated_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProfileDocumentRow(Base):
    __tablename__ = "profile_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(32), index=True)
    meta_json: Mapped[str] = mapped_column(Text)
    content: Mapped[bytes] = mapped_column(LargeBinary)


class AdmissionRow(Base):
    __tablename__ = "admissions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[str] = mapped_column(Text)


class HospitalPolicyRow(Base):
    """Every saved version of a hospital's rules. Versions are kept, never overwritten."""

    __tablename__ = "hospital_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer)
    policy_json: Mapped[str] = mapped_column(Text)
    saved_by: Mapped[str] = mapped_column(String(160))


class ResourceRow(Base):
    """A named, bookable hospital thing a desk can report unavailable."""

    __tablename__ = "resources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(String(160))
    hospital_id: Mapped[str] = mapped_column(String(32), index=True)
    department: Mapped[str] = mapped_column(String(64))


class CareStepRow(Base):
    __tablename__ = "care_steps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    scheduled_for: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    result_available_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    queue: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    patient: Mapped[PatientRow] = relationship(back_populates="steps")


class LedgerRow(Base):
    """Append-only. There is no update path and no delete path by design."""

    __tablename__ = "evidence_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(32), index=True)
    source: Mapped[str] = mapped_column(String(32))
    source_record_id: Mapped[str] = mapped_column(String(64))
    claim: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    previous_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True)
    #: The exact text that was hashed. `recorded_at` above is for querying; a
    #: database may drop its timezone, which would change the hash on reload.
    recorded_at_iso: Mapped[str] = mapped_column(String(40), default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class PlanRow(Base):
    __tablename__ = "visit_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(String(32), index=True)
    target_step_id: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(16))
    travel_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MessageRow(Base):
    """Every message, sent or diverted, with why."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(String(32), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("visit_plans.id"), nullable=True)
    language: Mapped[str] = mapped_column(String(8))
    channel: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(Text)
    routed_to_care_team: Mapped[bool] = mapped_column(Boolean, default=False)
    routing_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TurnaroundRow(Base):
    """Calibration data for the conformal predictor."""

    __tablename__ = "turnaround_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hospital_id: Mapped[str] = mapped_column(String(32), index=True)
    queue: Mapped[str] = mapped_column(String(64), index=True)
    days: Mapped[float] = mapped_column(Float)
    observed_on: Mapped[date] = mapped_column(Date, index=True)


class AlertRow(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    detail: Mapped[str] = mapped_column(Text)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class DisruptionRow(Base):
    """A reported outage. The body is the domain model as JSON, so a field added
    to `Disruption` needs no migration; the columns are only what is queried."""

    __tablename__ = "disruptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(64), index=True)
    unavailable_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text)


class ReadinessItemRow(Base):
    """One party's answer about one family's journey (a ride, a slot, an insurer)."""

    __tablename__ = "readiness_items"

    patient_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)


class OptionSetRow(Base):
    """Ranked options awaiting a human. One per patient, removed once approved."""

    __tablename__ = "option_sets"

    patient_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    disruption_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload_json: Mapped[str] = mapped_column(Text)


class ApprovalRow(Base):
    """Who approved which option, with a copy of the option. Append-only."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(32), index=True)
    disruption_id: Mapped[str] = mapped_column(String(36), index=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload_json: Mapped[str] = mapped_column(Text)


class ConsentRequestRow(Base):
    __tablename__ = "consent_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    abha_number: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[str] = mapped_column(Text)


class ConsentGrantRow(Base):
    __tablename__ = "consent_grants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    abha_number: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[str] = mapped_column(Text)


class RecordPointerRow(Base):
    """That a record exists and where. There is no column that could hold what it says."""

    __tablename__ = "record_pointers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    abha_number: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[str] = mapped_column(Text)


class AccessAttemptRow(Base):
    """Every attempt to open a record, allowed or refused. Append-only."""

    __tablename__ = "access_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    abha_number: Mapped[str] = mapped_column(String(32), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
