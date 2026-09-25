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
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PatientRow(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    home_district: Mapped[str] = mapped_column(String(128))
    home_distance_km: Mapped[float] = mapped_column(Float)
    language: Mapped[str] = mapped_column(String(8))
    caregiver_phone: Mapped[str] = mapped_column(String(24))
    hospital_id: Mapped[str] = mapped_column(String(32), index=True)

    steps: Mapped[list[CareStepRow]] = relationship(back_populates="patient")


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
