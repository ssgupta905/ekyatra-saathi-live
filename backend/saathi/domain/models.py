"""Domain models.

Boundary rule enforced here: nothing in this module has a field that can hold
report *content*. Status, timing and identifiers only.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    AlertKind,
    Channel,
    Decision,
    Language,
    SourceSystem,
    StepKind,
    StepStatus,
)


class Base(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Patient(Base):
    id: str
    #: Distance from home to the treating hospital. The number every metric
    #: in this project is ultimately denominated in.
    home_distance_km: float
    home_district: str
    language: Language
    caregiver_phone: str
    hospital_id: str


class CareStep(Base):
    """One node of a patient's journey."""

    id: str
    patient_id: str
    kind: StepKind
    status: StepStatus
    scheduled_for: date | None = None
    completed_on: date | None = None
    #: For report steps: when the result actually landed. Feeds the conformal
    #: calibration set.
    result_available_on: date | None = None
    #: Which department/hospital queue this sits in; turnaround is per-queue.
    queue: str | None = None


class ReadinessWindow(Base):
    """Calibrated interval for when a step's prerequisite becomes ready.

    Produced by split conformal prediction, so `earliest`..`latest` has a
    distribution-free coverage guarantee of at least `1 - alpha`.
    """

    step_id: str
    earliest: date
    latest: date
    alpha: float
    #: False when the calibration set was too small to give a real guarantee.
    calibrated: bool
    n_calibration: int


class BlockedPrerequisite(Base):
    """Why a visit cannot happen yet."""

    step_id: str
    kind: StepKind
    status: StepStatus
    expected_ready: ReadinessWindow | None = None


class EvidenceRef(Base):
    """A pointer from a sentence in a message back to the record that licenses it.

    The clinical guard rejects any message containing a claim without one.
    """

    ledger_id: str
    source: SourceSystem
    source_record_id: str


class VisitPlan(Base):
    """The planner's deterministic output. Claude never produces one of these."""

    patient_id: str
    target_step_id: str
    decision: Decision
    #: Only set when decision is GO. WAIT and UNCERTAIN never promise a date.
    travel_on: date | None = None
    #: Steps that can be collapsed into the same trip as the target.
    bundled_step_ids: tuple[str, ...] = ()
    blocked_by: tuple[BlockedPrerequisite, ...] = ()
    what_to_bring: tuple[str, ...] = ()
    where_to_go_first: str | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    rationale: str = ""


class CaregiverMessage(Base):
    """What Claude is allowed to produce: language, bound to a plan.

    Every field is rendered from `VisitPlan`; the guard re-checks that the
    rendered text asserts nothing the plan does not.
    """

    patient_id: str
    language: Language
    channel: Channel
    body: str
    evidence: tuple[EvidenceRef, ...]
    #: Set when the guard diverted the message instead of sending it.
    routed_to_care_team: bool = False
    routing_reason: str | None = None


class EngagementSignal(Base):
    """One observation in the caregiver's response series."""

    patient_id: str
    observed_at: datetime
    #: Hours between Saathi's message and the caregiver's reply. A rising
    #: series is the disengagement signal PELT looks for.
    response_latency_hours: float
    responded: bool


class Alert(Base):
    id: str
    patient_id: str
    kind: AlertKind
    raised_at: datetime
    detail: str
    evidence: tuple[EvidenceRef, ...] = ()


class TripOutcome(Base):
    """The measurement the whole project is judged on."""

    patient_id: str
    trips_taken: int
    #: Trips where the family travelled and the step could not happen.
    wasted_trips: int
    days_in_city: int
    non_medical_cost_inr: float = Field(ge=0)
