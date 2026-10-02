"""State carried through the planner graph."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import TypedDict

from ..domain.enums import Decision, StepKind
from ..domain.models import (
    BlockedPrerequisite,
    CaregiverMessage,
    CareStep,
    EvidenceRef,
    Patient,
    VisitPlan,
)


class PlannerState(TypedDict, total=False):
    """Mutable working set for one planning run.

    Inputs are set by the caller; every other key is produced by a node. Keys
    are never removed, so a completed run is a full audit trail of how the plan
    was reached.
    """

    # --- inputs ---
    patient: Patient
    steps: Sequence[CareStep]
    target_kind: StepKind
    today: date
    #: Set False to decide without calling the language layer. The live runner
    #: plans every patient every day but only renders the ones that changed.
    compose: bool

    # --- derived ---
    target: CareStep | None
    blockers: tuple[BlockedPrerequisite, ...]
    missing_kinds: frozenset[StepKind]
    decision: Decision
    travel_on: date | None
    bundled_step_ids: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]

    # --- outputs ---
    plan: VisitPlan | None
    message: CaregiverMessage | None
    #: Set when the run ended in something a human must look at.
    escalation: str | None
    #: Measured wall-clock cost of this run, in milliseconds. The live console
    #: shows these, so they are timed rather than estimated.
    plan_ms: float
    render_ms: float
