"""Typed tools the planner is built from.

Each function is a pure, side-effect-light unit with an explicit signature. They
are separated from the graph so they can be tested without a graph runtime, and
so the set of things the planner can *do* is enumerable on one screen.

None of these are exposed to Claude. The language layer has no tools at all.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta

from ..domain.enums import (
    REPORT_STEPS,
    TRAVEL_STEPS,
    Decision,
    ReadinessStatus,
    SourceSystem,
    StepKind,
    StepStatus,
)
from ..domain.models import (
    BlockedPrerequisite,
    CareStep,
    Disruption,
    MaintenanceCycle,
    ReadinessItem,
    ReadinessWindow,
)
from ..domain.pathway import ONCOLOGY, Pathway
from ..domain.policy import ENTITLEMENTS
from ..graph.dependencies import DependencyGraph
from ..ports.ledger import EvidenceLedger
from ..readiness.bookings import window_from_booking
from ..readiness.conformal import ConformalReadinessPredictor

#: Statuses that satisfy a prerequisite.
SATISFIED = frozenset({StepStatus.COMPLETED, StepStatus.RESULT_AVAILABLE})


def find_step(steps: Sequence[CareStep], kind: StepKind) -> CareStep | None:
    """The patient's step of a given kind, if the journey has one."""
    for step in steps:
        if step.kind is kind:
            return step
    return None


def unmet_prerequisites(
    target: CareStep,
    steps: Sequence[CareStep],
    graph: DependencyGraph,
) -> tuple[CareStep, ...]:
    """Prerequisite steps of `target` that are not yet satisfied.

    Walks transitive ancestors, not just direct parents: a scan whose radiology
    report is pending blocks the review consult even though the scan itself is
    marked complete.
    """
    unmet: list[CareStep] = []
    for kind in graph.transitive_prerequisites(target.kind):
        step = find_step(steps, kind)
        if step is None:
            # The journey has no such step recorded. We cannot prove it is
            # satisfied, so it counts as unmet and drives UNCERTAIN.
            continue
        if step.status not in SATISFIED:
            unmet.append(step)
    return tuple(unmet)


def missing_prerequisite_kinds(
    target: CareStep,
    steps: Sequence[CareStep],
    graph: DependencyGraph,
) -> frozenset[StepKind]:
    """Prerequisite kinds with no corresponding record at all.

    Absence of evidence is not evidence of readiness — these force UNCERTAIN.
    """
    present = {s.kind for s in steps}
    return frozenset(graph.transitive_prerequisites(target.kind) - present)


def readiness_for(
    step: CareStep,
    predictor: ConformalReadinessPredictor,
) -> ReadinessWindow | None:
    """Conformal window for when a pending report will land.

    Only meaningful for report steps that are awaiting a result and whose
    procedure date is known.
    """
    if step.kind not in REPORT_STEPS:
        return None
    if step.status is not StepStatus.PENDING_RESULT:
        return None
    anchor = step.completed_on or step.scheduled_for
    if anchor is None or not step.queue:
        return None
    return predictor.window(step.id, step.queue, anchor)


def describe_blockers(
    unmet: Iterable[CareStep],
    predictor: ConformalReadinessPredictor,
    disruptions: Iterable[Disruption] = (),
) -> tuple[BlockedPrerequisite, ...]:
    """Why each unmet prerequisite is unmet, and when it is expected to clear.

    Two different questions share this field. A pending *report* gets a
    conformal forecast; a *booked* step gets the day the hospital committed to,
    which is a record rather than a prediction. A booking the disruption list
    has invalidated gets neither — `None` here is what drives the plan to
    UNCERTAIN the moment a machine goes down.
    """
    active = tuple(disruptions)
    return tuple(
        BlockedPrerequisite(
            step_id=step.id,
            kind=step.kind,
            status=step.status,
            expected_ready=(
                readiness_for(step, predictor)
                or window_from_booking(step, active)
            ),
        )
        for step in unmet
    )


def decide(
    blockers: Sequence[BlockedPrerequisite],
    missing_kinds: frozenset[StepKind],
    today: date,
) -> Decision:
    """The go/wait decision. This is the whole safety argument in one function.

    - Any prerequisite with no record at all -> UNCERTAIN. We do not guess.
    - Any blocker whose readiness window is uncalibrated or absent -> UNCERTAIN.
      An uncalibrated window is not a date we are willing to put a family's
      savings behind.
    - Any blocker still pending -> WAIT.
    - Otherwise -> GO.
    """
    if missing_kinds:
        return Decision.UNCERTAIN

    for blocker in blockers:
        window = blocker.expected_ready
        if window is None or not window.calibrated:
            return Decision.UNCERTAIN

    if blockers:
        return Decision.WAIT

    return Decision.GO


def relevant_items(
    items: Iterable[ReadinessItem], step_ids: Iterable[str]
) -> tuple[ReadinessItem, ...]:
    """The items that gate this visit: its own, and those gating "the next visit"."""
    wanted = set(step_ids)
    return tuple(i for i in items if i.step_id is None or i.step_id in wanted)


def decide_with_items(base: Decision, items: Sequence[ReadinessItem]) -> Decision:
    """Fold the other parties' answers into the care-step decision.

    Severity runs UNCERTAIN > WAIT > REPLAN > GO, and a party can only make the
    answer more cautious, never less: a ride that is ready does not clear a
    report that is not.

    - A party nobody has heard from -> UNCERTAIN. Silence is not readiness.
    - Pending -> WAIT.
    - Blocked with another way available -> REPLAN; blocked with none -> WAIT.
    """
    if base in (Decision.UNCERTAIN, Decision.WAIT):
        return base
    if any(i.status is ReadinessStatus.UNKNOWN for i in items):
        return Decision.UNCERTAIN
    blocked = [i for i in items if i.status is ReadinessStatus.BLOCKED]
    if any(not i.alternative_available for i in blocked):
        return Decision.WAIT
    if any(i.status is ReadinessStatus.PENDING for i in items):
        return Decision.WAIT
    if blocked:
        return Decision.REPLAN
    return base


def earliest_safe_travel_date(
    blockers: Sequence[BlockedPrerequisite],
    today: date,
    lead_days: int = 1,
) -> date | None:
    """First date on which every blocker is expected to be ready.

    Uses the *upper* bound of each conformal interval, not the point estimate:
    the asymmetry is intentional, because arriving a day early wastes a trip and
    arriving a day late costs a day of lodging.
    """
    if not blockers:
        return today + timedelta(days=lead_days)
    latest = []
    for blocker in blockers:
        if blocker.expected_ready is None or not blocker.expected_ready.calibrated:
            return None
        latest.append(blocker.expected_ready.latest)
    return max(latest) + timedelta(days=lead_days)


def bundle_steps(
    target: CareStep,
    steps: Sequence[CareStep],
    graph: DependencyGraph,
) -> tuple[str, ...]:
    """Other steps that can be folded into the same trip as `target`.

    This is where trips actually get saved: the deck's four-trip journey becomes
    two because consult + biopsy + bloods collapse into one visit.
    """
    candidates = [
        step
        for step in steps
        if step.id != target.id
        and step.kind in TRAVEL_STEPS
        and step.status not in SATISFIED
        and step.status is not StepStatus.CANCELLED
        and graph.can_share_trip(target.kind, step.kind)
    ]

    # A prerequisite that happens on this same trip is satisfied by this trip.
    # The biopsy needs the consult, but consult and biopsy are co-locatable, so
    # requiring the consult to be already complete would refuse the very
    # bundling that saves the family a journey. Steps in the trip are therefore
    # excluded from each other's unmet set — but nothing else is, so a review
    # consult still cannot ride along while its reports are pending.
    in_trip = {target.id} | {step.id for step in candidates}

    bundled: list[str] = []
    for step in candidates:
        outstanding = [
            prereq
            for prereq in unmet_prerequisites(step, steps, graph)
            if prereq.id not in in_trip
        ]
        if outstanding:
            continue
        bundled.append(step.id)
    return tuple(bundled)


#: What to carry. Logistics only — no medication lists, which would be clinical.
BASE_DOCUMENTS: tuple[str, ...] = (
    "hospital file / patient ID card",
    "ABHA number or Ayushman card",
    "previous appointment slips",
)

#: Oncology's per-step documents, under their old name. Other pathways carry
#: their own on `Pathway.documents`.
STEP_DOCUMENTS = ONCOLOGY.documents


def documents_to_bring(
    target: CareStep,
    bundled_kinds: Iterable[StepKind],
    requirements: Mapping[str, Sequence[str]] | None = None,
    pathway: Pathway = ONCOLOGY,
) -> tuple[str, ...]:
    """What to carry: the common list, each step's own, then what this hospital asks for.

    `requirements` is the hospital's saved rules (step kind -> document ids).
    A hospital that has said nothing asks for nothing extra.
    """
    kinds = (target.kind, *bundled_kinds)
    items = list(BASE_DOCUMENTS)
    for kind in kinds:
        for doc in pathway.documents.get(kind, ()):
            if doc not in items:
                items.append(doc)
    for kind in kinds:
        for doc_id in (requirements or {}).get(kind.value, ()):
            label = ENTITLEMENTS.get(doc_id, doc_id)
            # "Hospital file / patient ID card" is already on the common list
            # in lower case; asking twice for one card helps nobody.
            if label.lower() not in {item.lower() for item in items}:
                items.append(label)
    return tuple(items)


#: Which desk to reach first. Ordering matters: the first queue of the day is
#: the one that determines whether the family gets home the same night.
FIRST_STOP = ONCOLOGY.first_stop


def where_to_go_first(
    target: CareStep,
    bundled_kinds: Sequence[StepKind],
    pathway: Pathway = ONCOLOGY,
) -> str | None:
    # Bloods first when bundled: the sample counter closes earliest and the
    # rest of the day can proceed while it runs.
    if StepKind.BLOODS in bundled_kinds and StepKind.BLOODS in pathway.first_stop:
        return pathway.first_stop[StepKind.BLOODS]
    return pathway.first_stop.get(target.kind)


def record_status_evidence(
    ledger: EvidenceLedger,
    patient_id: str,
    steps: Sequence[CareStep],
    relevant_ids: Iterable[str],
) -> tuple:
    """Write one ledger entry per fact the plan relies on; return the refs.

    `record_once`, not `record`: planning the same unchanged patient again must
    not grow the chain. A new row here means a fact about this patient actually
    changed.
    """
    wanted = set(relevant_ids)
    refs = []
    for step in steps:
        if step.id not in wanted:
            continue
        entry = ledger.record_once(
            patient_id=patient_id,
            source=SourceSystem.ABDM if step.kind in REPORT_STEPS else SourceSystem.HOSPITAL_FEED,
            source_record_id=step.id,
            claim=f"{step.kind.value} is {step.status.value}",
            metadata={
                "scheduled_for": step.scheduled_for.isoformat() if step.scheduled_for else None,
                "queue": step.queue,
            },
        )
        refs.append(entry.ref())
    return tuple(refs)


#: Maintenance is a recurring step: the 1-indexed dose numbers that need an
#: echo + review bundled first, per the advising doctor's sketch.
ECHO_GATED_DOSES = ONCOLOGY.recurrence.gated_indices if ONCOLOGY.recurrence else frozenset()


def requires_echo_bundle(dose_index: int, pathway: Pathway = ONCOLOGY) -> bool:
    """Whether this dose number needs an echo + review bundled before it.

    A plain lookup, not a clinical judgement — the doctor set the gated
    doses; this function only remembers which ones they were.
    """
    return pathway.requires_companion(dose_index)


def due_dose(cycle: MaintenanceCycle, today: date) -> int | None:
    """Which dose number is due today or earlier, if any.

    None when the cycle is finished or the next dose isn't due yet.
    """
    if cycle.dose_index > cycle.total_doses:
        return None
    due_on = cycle.anchor_date + timedelta(days=cycle.interval_days * (cycle.dose_index - 1))
    if due_on > today:
        return None
    return cycle.dose_index


def next_dose_not_before(cycle: MaintenanceCycle, completed_doses: int) -> date:
    """Earliest date the next dose after `completed_doses` may be given.

    Doses are spaced by `interval_days` from the anchor, not from whenever
    the previous one actually happened — a delayed dose does not compress
    the gap before the one after it.
    """
    return cycle.anchor_date + timedelta(days=cycle.interval_days * completed_doses)
