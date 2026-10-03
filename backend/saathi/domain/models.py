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
    DisruptionKind,
    FamilyMemberRole,
    Language,
    ResourceKind,
    Role,
    SourceSystem,
    StepKind,
    StepStatus,
)


class Base(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FamilyMember(Base):
    """One person in a family, each with their own channel and language.

    A caregiver and the patient themself are not the same person and may
    legitimately be told the same fact on different channels.
    """

    id: str
    patient_id: str
    role: FamilyMemberRole
    name: str
    phone: str
    preferred_channel: Channel
    language: Language


class Patient(Base):
    id: str
    #: Distance from home to the treating hospital. The number every metric
    #: in this project is ultimately denominated in.
    home_distance_km: float
    home_district: str
    language: Language
    caregiver_phone: str
    hospital_id: str
    family_members: tuple[FamilyMember, ...] = ()


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
    #: The specific bookable resource (machine, staff, supply) this step
    #: needs, when disruption tracking cares which one. None for steps that
    #: don't book against a named resource.
    resource_id: str | None = None


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


class Resource(Base):
    """A named, bookable hospital thing: a machine, a staff role, a supply.

    Disruptions are raised against a resource; `affected_patients` matches
    steps to it by id or by department/kind, never by report content.
    """

    id: str
    kind: ResourceKind
    display_name: str
    hospital_id: str
    department: str


class Disruption(Base):
    """A desk's one-tap report that a resource is unavailable for a window.

    `note` is logistics text only ("MRI-2 down for service") — the same
    content boundary as everywhere else in this module.
    """

    id: str
    resource_id: str
    kind: DisruptionKind
    raised_by: SourceSystem
    raised_at: datetime
    unavailable_from: date
    unavailable_to: date | None = None
    note: str = ""


class PlanOption(Base):
    """One candidate re-plan for a disrupted patient, with its tradeoffs.

    Shaped like `VisitPlan` plus the numbers a person needs to pick between
    options. There is no score field: the list's order is the only
    ranking, produced by a documented deterministic sort, never a stored
    composite number a navigator could mistake for the system deciding.
    """

    patient_id: str
    target_step_id: str
    decision: Decision
    travel_on: date | None = None
    bundled_step_ids: tuple[str, ...] = ()
    blocked_by: tuple[BlockedPrerequisite, ...] = ()
    what_to_bring: tuple[str, ...] = ()
    where_to_go_first: str | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    rationale: str = ""
    #: The date the target step itself lands on under this option. Distinct
    #: from `travel_on`, which answers "when may they set out" and for an
    #: unblocked plan is simply tomorrow. When an option is about *moving an
    #: appointment*, this is the number that matters, and checking tolerance
    #: against `travel_on` silently compares the wrong two dates.
    target_on: date | None = None
    #: Nights added to the family's stay versus the pre-disruption plan.
    #: Negative when the option shortens the stay.
    nights_added: int = 0
    #: Extra trips versus the pre-disruption plan. Negative when the option
    #: removes a trip (the stock-late "better than before" case).
    extra_trips: int = 0
    #: Days a maintenance dose is delayed by this option. 0 outside
    #: maintenance.
    dose_delay_days: int = 0
    #: Journeys this option needs sooner than a reserved seat can be obtained.
    #: A plan that assumes a berth from Gaya to Mumbai the day after tomorrow
    #: is not merely expensive, it may be impossible — and a family told to
    #: travel on a train they cannot board has been failed worse than one told
    #: to wait. Always 0 where the journey is short enough to take on the day.
    short_notice_journeys: int = 0


class MaintenanceCycle(Base):
    """A patient's repeating post-treatment dosing schedule."""

    patient_id: str
    dose_index: int
    total_doses: int = 17
    interval_days: int = 21
    anchor_date: date
    #: True on the doses that require an echo + review bundled first.
    requires_echo: bool = False


class ApprovalDecision(Base):
    """The one human action that turns a chosen `PlanOption` into a plan.

    `option_summary` is a copy, not a reference, so the audit trail reads
    correctly even if the option list is recomputed later.
    """

    id: str
    patient_id: str
    disruption_id: str
    option_summary: PlanOption
    approved_by_role: Role
    approved_by: str
    approved_at: datetime
    evidence: tuple[EvidenceRef, ...] = ()


class HoldingMessage(Base):
    """"Don't travel yet" — sent before any new date is known.

    Distinct from `CaregiverMessage`: it is not bound to a `VisitPlan`
    because, by construction, no new plan exists yet when it is sent. It
    still carries evidence — the disruption itself — so the guard's "no
    source, no message" rule holds here too.
    """

    patient_id: str
    disruption_id: str
    language: Language
    channel: Channel
    body: str
    evidence: tuple[EvidenceRef, ...]
    sent_at: datetime


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
