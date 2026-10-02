"""Typed tools the planner is built from.

Each function is a pure, side-effect-light unit with an explicit signature. They
are separated from the graph so they can be tested without a graph runtime, and
so the set of things the planner can *do* is enumerable on one screen.

None of these are exposed to Claude. The language layer has no tools at all.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from ..domain.enums import (
    REPORT_STEPS,
    TRAVEL_STEPS,
    Decision,
    SourceSystem,
    StepKind,
    StepStatus,
)
from ..domain.models import BlockedPrerequisite, CareStep, ReadinessWindow
from ..graph.dependencies import DependencyGraph
from ..ledger.evidence import InMemoryEvidenceLedger
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
) -> tuple[BlockedPrerequisite, ...]:
    return tuple(
        BlockedPrerequisite(
            step_id=step.id,
            kind=step.kind,
            status=step.status,
            expected_ready=readiness_for(step, predictor),
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

STEP_DOCUMENTS: dict[StepKind, tuple[str, ...]] = {
    StepKind.SCAN: ("scan request form", "previous scan films if you have them"),
    StepKind.BLOODS: ("blood test request form", "come without eating if told to"),
    StepKind.BIOPSY: ("biopsy consent form", "someone to travel back with you"),
    StepKind.REVIEW_CONSULT: ("all report slips collected so far",),
    StepKind.TREATMENT: ("admission letter", "payment or scheme documents"),
}


def documents_to_bring(target: CareStep, bundled_kinds: Iterable[StepKind]) -> tuple[str, ...]:
    items = list(BASE_DOCUMENTS)
    for kind in (target.kind, *bundled_kinds):
        for doc in STEP_DOCUMENTS.get(kind, ()):
            if doc not in items:
                items.append(doc)
    return tuple(items)


#: Which desk to reach first. Ordering matters: the first queue of the day is
#: the one that determines whether the family gets home the same night.
FIRST_STOP: dict[StepKind, str] = {
    StepKind.CONSULT: "OPD registration counter",
    StepKind.BIOPSY: "OPD registration counter",
    StepKind.BLOODS: "sample collection counter",
    StepKind.SCAN: "radiology reception",
    StepKind.REVIEW_CONSULT: "OPD registration counter",
    StepKind.TREATMENT: "admission desk",
}


def where_to_go_first(target: CareStep, bundled_kinds: Sequence[StepKind]) -> str | None:
    # Bloods first when bundled: the sample counter closes earliest and the
    # rest of the day can proceed while it runs.
    if StepKind.BLOODS in bundled_kinds:
        return FIRST_STOP[StepKind.BLOODS]
    return FIRST_STOP.get(target.kind)


def record_status_evidence(
    ledger: InMemoryEvidenceLedger,
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
