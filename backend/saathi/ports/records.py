"""Where a hospital's records live between restarts.

The live world keeps its working set in memory because planning reads it
constantly. A `RecordStore` is what that working set is loaded from at startup
and written through to on every change, so a restart loses nothing.

Two adapters satisfy it: one in memory (tests, and the demo, which should not
leave files behind) and one over SQLAlchemy (SQLite now, Postgres by changing a
URL). The world never learns which it has.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from ..domain.enums import StepKind
from ..domain.models import (
    ApprovalDecision,
    CareStep,
    Disruption,
    Patient,
    PlanOption,
    ReadinessItem,
    Resource,
)


@dataclass(frozen=True)
class TurnaroundObservation:
    """One report that took `days` from sample to release, in a given queue."""

    queue: str
    days: float
    observed_on: date
    hospital_id: str = ""


@dataclass(frozen=True)
class StoredOptionSet:
    """Ranked options waiting for a navigator or doctor, as kept between restarts."""

    patient_id: str
    disruption_id: str
    options: tuple[PlanOption, ...]
    created_at: datetime


@dataclass(frozen=True)
class StoredRecords:
    patients: tuple[Patient, ...] = ()
    steps: dict[str, tuple[CareStep, ...]] = field(default_factory=dict)
    resources: tuple[Resource, ...] = ()
    #: patient id -> the step kind that family is planned towards.
    plan_targets: dict[str, StepKind] = field(default_factory=dict)
    turnaround: tuple[TurnaroundObservation, ...] = ()
    #: Orchestration state. Plans are not here: the planner recomputes them from
    #: the records above, so storing them could only ever drift from the truth.
    disruptions: tuple[Disruption, ...] = ()
    readiness_items: tuple[ReadinessItem, ...] = ()
    option_sets: tuple[StoredOptionSet, ...] = ()
    approvals: tuple[ApprovalDecision, ...] = ()


class RecordStore(Protocol):
    def load(self) -> StoredRecords:
        """Everything, for building the world at startup."""
        ...

    def save_patient(self, patient: Patient, plan_target: StepKind | None = None) -> None:
        """Insert or replace a patient and their family members."""
        ...

    def save_step(self, step: CareStep) -> None:
        """Insert or replace one care step."""
        ...

    def save_resource(self, resource: Resource) -> None: ...

    def add_turnaround(self, observation: TurnaroundObservation) -> None: ...

    def save_disruption(self, disruption: Disruption) -> None: ...

    def save_readiness_item(self, item: ReadinessItem) -> None:
        """Insert or replace one party's answer."""
        ...

    def delete_readiness_item(self, patient_id: str, item_id: str) -> None: ...

    def save_option_set(self, option_set: StoredOptionSet) -> None:
        """One pending set per patient; a new one replaces the old."""
        ...

    def delete_option_set(self, patient_id: str) -> None: ...

    def add_approval(self, approval: ApprovalDecision) -> None:
        """Append-only: an approval is never edited or removed."""
        ...
