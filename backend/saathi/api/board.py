"""The plan board: one patient's whole pathway, laid out.

A navigator holding thirty families needs to see a journey the way it actually
is — a branching chain where one pending report holds up a consultation that
holds up everything after it — not a list of rows sorted by date. A list hides
the thing that matters, which is *what is waiting on what*.

So the layout is computed here rather than in the console. Depth through the
dependency DAG is a property of the care pathway, and the pathway is the
backend's business; a console that worked it out for itself would be a second
place the hospital's model of care lived, and the two would drift. The console
receives columns and edges and draws them.

Everything on a board is status and timing. There is no field here that could
carry a finding, and the one piece of clinical vocabulary — the step's own name
— is the same vocabulary the family's appointment slip uses.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..domain.enums import REPORT_STEPS, Decision, StepKind, StepStatus
from ..domain.pathway import get_pathway
from ..graph.dependencies import DependencyGraph
from .access import AnyStaff
from .deps import ContainerDep

logger = logging.getLogger(__name__)

router = APIRouter()

#: Statuses that mean nothing further is waiting on this step.
SATISFIED = frozenset({StepStatus.COMPLETED, StepStatus.RESULT_AVAILABLE})

STEP_LABELS: dict[StepKind, str] = {
    StepKind.CONSULT: "First consult",
    StepKind.BIOPSY: "Biopsy",
    StepKind.BLOODS: "Blood tests",
    StepKind.SCAN: "Scan",
    StepKind.PET_CT: "PET-CT",
    StepKind.PATHOLOGY_REPORT: "Pathology report",
    StepKind.RADIOLOGY_REPORT: "Radiology report",
    StepKind.REVIEW_CONSULT: "Review consult",
    StepKind.JOINT_CLINIC: "Joint clinic",
    StepKind.TREATMENT: "Treatment",
    StepKind.MAINTENANCE_DOSE: "Maintenance dose",
    StepKind.ECHO_REVIEW: "Echo + review",
}


def _depths(graph: DependencyGraph, edges) -> dict[str, int]:
    """How far down the pathway each kind sits.

    The longest path to a node, not the shortest: a review consult waits for
    the slowest of its prerequisites, and drawing it beside the fastest would
    misrepresent the wait that actually exists.
    """
    depth: dict[StepKind, int] = {}

    def resolve(kind: StepKind, seen: frozenset[StepKind]) -> int:
        if kind in depth:
            return depth[kind]
        if kind in seen:  # defensive; the graph is validated as a DAG on build
            return 0
        parents = graph.prerequisites(kind)
        value = 0 if not parents else 1 + max(
            resolve(parent, seen | {kind}) for parent in parents
        )
        depth[kind] = value
        return value

    for parent, child in edges:
        resolve(parent, frozenset())
        resolve(child, frozenset())
    return {kind.value: value for kind, value in depth.items()}


def _node(
    step,
    graph: DependencyGraph,
    depths: dict[str, int],
    target_id: str | None,
    blocked_ids: set[str],
) -> dict:
    satisfied = step.status in SATISFIED
    return {
        "id": step.id,
        "kind": step.kind.value,
        "label": STEP_LABELS.get(step.kind, step.kind.value.replace("_", " ")),
        "status": step.status.value,
        "scheduled_for": step.scheduled_for.isoformat() if step.scheduled_for else None,
        "completed_on": step.completed_on.isoformat() if step.completed_on else None,
        "result_available_on": (
            step.result_available_on.isoformat() if step.result_available_on else None
        ),
        "queue": step.queue,
        "resource_id": step.resource_id,
        "column": depths.get(step.kind.value, 0),
        "satisfied": satisfied,
        "is_target": step.id == target_id,
        "is_blocking": step.id in blocked_ids,
        #: Report steps are drawn differently: nobody travels for them.
        "no_journey": step.kind in REPORT_STEPS,
        "depends_on": sorted(k.value for k in graph.prerequisites(step.kind)),
    }


def build_board(state, patient_id: str) -> dict:
    """One patient's pathway, with the plan's verdict laid over it."""
    patient = state.world.patient(patient_id)
    if patient is None:
        raise HTTPException(404, "unknown patient")

    steps = state.world.steps_for(patient_id)
    run = state.runner.plans.get(patient_id)
    plan = run.plan if run else None
    pathway = get_pathway(patient.pathway_id)
    graph = state.planner.graph_for(patient)

    target_id = plan.target_step_id if plan else None
    blocked_ids = {b.step_id for b in plan.blocked_by} if plan else set()
    present = {s.kind.value for s in steps}

    depths = _depths(graph, pathway.edges)
    nodes = [_node(step, graph, depths, target_id, blocked_ids) for step in steps]
    nodes.sort(key=lambda n: (n["column"], n["label"]))

    # Only edges between steps this patient actually has. A pathway edge to a
    # step nobody ordered is not part of this journey and drawing it would
    # imply a wait that does not exist.
    edges = [
        {"from": parent.value, "to": child.value}
        for parent, child in pathway.edges
        if parent.value in present and child.value in present
    ]

    return {
        "patient": {
            "id": patient.id,
            "district": patient.home_district,
            "language": patient.language.value,
            "distance_km": round(patient.home_distance_km),
        },
        "decision": plan.decision.value if plan else None,
        "travel_on": plan.travel_on.isoformat() if plan and plan.travel_on else None,
        "rationale": plan.rationale if plan else "",
        "target_step_id": target_id,
        "computed_at": run.computed_at.isoformat() if run else None,
        "plan_ms": run.plan_ms if run else None,
        "sim_date": state.world.today.isoformat(),
        "nodes": nodes,
        "edges": edges,
        "columns": (max((n["column"] for n in nodes), default=0) + 1),
        "waiting_on": [
            {
                "step_id": b.step_id,
                "label": STEP_LABELS.get(b.kind, b.kind.value.replace("_", " ")),
                "status": b.status.value,
                "earliest": b.expected_ready.earliest.isoformat() if b.expected_ready else None,
                "latest": b.expected_ready.latest.isoformat() if b.expected_ready else None,
                "calibrated": b.expected_ready.calibrated if b.expected_ready else False,
                #: A booking is a fact rather than a forecast, and the board
                #: should not quote a coverage level at one.
                "from_booking": bool(
                    b.expected_ready
                    and b.expected_ready.n_calibration == 0
                    and b.expected_ready.earliest == b.expected_ready.latest
                ),
            }
            for b in (plan.blocked_by if plan else ())
        ],
    }


@router.get("/patients/{patient_id}/board", dependencies=[AnyStaff])
async def patient_board(state: ContainerDep, patient_id: str) -> dict:
    return build_board(state, patient_id)


@router.get("/boards", dependencies=[AnyStaff])
async def boards(state: ContainerDep, watched: bool = True, limit: int = 500) -> dict:
    """Every board a navigator is holding, worst first.

    Ordered by how much is in the family's way, then by how far they would have
    to travel — not by a score. There is no ranking number here and no field to
    put one in; the order is a consequence of two facts a navigator can see.
    """
    ids = list(state.world.watched) if watched else [p.id for p in state.world.patients()]

    built = [build_board(state, pid) for pid in ids[:limit]]
    rank = {
        Decision.UNCERTAIN.value: 0,
        Decision.REPLAN.value: 1,
        Decision.WAIT.value: 2,
        Decision.GO.value: 3,
    }
    built.sort(
        key=lambda b: (
            rank.get(b["decision"], 4),
            -len(b["waiting_on"]),
            -b["patient"]["distance_km"],
        )
    )
    return {"boards": built, "sim_date": state.world.today.isoformat()}
