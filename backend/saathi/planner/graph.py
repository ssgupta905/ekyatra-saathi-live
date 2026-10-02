"""The planner graph.

LangGraph is used here for its explicit state machine and its checkpointing, not
for model-driven control flow. Every edge in this graph is decided by code; the
model is called in exactly one node (`compose`) and cannot influence routing.
That is the point. An agent that could choose its own path could choose to tell
a family to travel.

    load -> dependencies -> readiness -> decide -> bundle -> evidence -> compose
                                            |
                                            +-> escalate (uncertain / no target)
"""

from __future__ import annotations

import logging
from datetime import date
from time import perf_counter

from langgraph.graph import END, START, StateGraph

from ..domain.enums import Channel, Decision, StepKind
from ..domain.models import CareStep, Patient, VisitPlan
from ..graph.dependencies import DependencyGraph, InMemoryDependencyGraph
from ..language.claude import ClaudeLanguageLayer
from ..ledger.evidence import InMemoryEvidenceLedger
from ..readiness.conformal import ConformalReadinessPredictor
from . import tools
from .state import PlannerState

logger = logging.getLogger(__name__)


class VisitPlanner:
    """Builds and runs the planning graph for one hospital's patients."""

    def __init__(
        self,
        dependency_graph: DependencyGraph | None = None,
        predictor: ConformalReadinessPredictor | None = None,
        ledger: InMemoryEvidenceLedger | None = None,
        language_layer: ClaudeLanguageLayer | None = None,
    ) -> None:
        self.graph = dependency_graph or InMemoryDependencyGraph()
        self.predictor = predictor or ConformalReadinessPredictor()
        self.ledger = ledger or InMemoryEvidenceLedger()
        #: Optional so the planner can be exercised without API credentials —
        #: the demo and the tests run the full decision path with it unset.
        self.language_layer = language_layer
        self._compiled = self._build().compile()

    # ---------------- nodes ----------------

    def _load(self, state: PlannerState) -> PlannerState:
        target = tools.find_step(state["steps"], state["target_kind"])
        return {"target": target}

    def _dependencies(self, state: PlannerState) -> PlannerState:
        target = state.get("target")
        if target is None:
            return {"blockers": (), "missing_kinds": frozenset()}
        unmet = tools.unmet_prerequisites(target, state["steps"], self.graph)
        missing = tools.missing_prerequisite_kinds(target, state["steps"], self.graph)
        return {
            "blockers": tools.describe_blockers(unmet, self.predictor),
            "missing_kinds": missing,
        }

    def _readiness(self, state: PlannerState) -> PlannerState:
        # Blockers already carry their conformal windows from `describe_blockers`.
        # This node exists as the place to add cross-queue contention modelling
        # in the pilot without reshaping the graph.
        return {}

    def _decide(self, state: PlannerState) -> PlannerState:
        if state.get("target") is None:
            return {
                "decision": Decision.UNCERTAIN,
                "escalation": f"no {state['target_kind'].value} step on record",
            }
        decision = tools.decide(
            state["blockers"], state["missing_kinds"], state["today"]
        )
        travel_on = None
        if decision is Decision.GO:
            travel_on = tools.earliest_safe_travel_date([], state["today"])
        return {"decision": decision, "travel_on": travel_on}

    def _bundle(self, state: PlannerState) -> PlannerState:
        target = state.get("target")
        if target is None or state["decision"] is not Decision.GO:
            return {"bundled_step_ids": ()}
        return {
            "bundled_step_ids": tools.bundle_steps(target, state["steps"], self.graph)
        }

    def _evidence(self, state: PlannerState) -> PlannerState:
        target = state.get("target")
        relevant = {b.step_id for b in state.get("blockers", ())}
        relevant.update(state.get("bundled_step_ids", ()))
        if target is not None:
            relevant.add(target.id)
        refs = tools.record_status_evidence(
            self.ledger, state["patient"].id, state["steps"], relevant
        )

        target_id = target.id if target else ""
        bundled_kinds = [
            s.kind for s in state["steps"] if s.id in state.get("bundled_step_ids", ())
        ]
        plan = VisitPlan(
            patient_id=state["patient"].id,
            target_step_id=target_id,
            decision=state["decision"],
            travel_on=state.get("travel_on"),
            bundled_step_ids=state.get("bundled_step_ids", ()),
            blocked_by=state.get("blockers", ()),
            what_to_bring=(
                tools.documents_to_bring(target, bundled_kinds)
                if target and state["decision"] is Decision.GO
                else ()
            ),
            where_to_go_first=(
                tools.where_to_go_first(target, bundled_kinds)
                if target and state["decision"] is Decision.GO
                else None
            ),
            evidence=refs,
            rationale=_rationale(state),
        )
        return {"evidence": refs, "plan": plan}

    def _compose(self, state: PlannerState) -> PlannerState:
        plan = state.get("plan")
        if plan is None or self.language_layer is None:
            return {}
        if state.get("compose", True) is False:
            # Deciding and speaking are separable, and the live runner decides
            # for everyone but speaks only to the families whose answer changed.
            return {}
        started = perf_counter()
        message = self.language_layer.render(
            plan=plan,
            language=state["patient"].language,
            channel=Channel.WHATSAPP,
            ledger=self.ledger,
        )
        update: PlannerState = {
            "message": message,
            "render_ms": (perf_counter() - started) * 1000,
        }
        if message.routed_to_care_team:
            update["escalation"] = message.routing_reason
        return update

    def _escalate(self, state: PlannerState) -> PlannerState:
        reason = state.get("escalation") or "plan could not be determined"
        logger.info("escalating %s: %s", state["patient"].id, reason)
        return {"escalation": reason}

    # ---------------- wiring ----------------

    def _route_after_decide(self, state: PlannerState) -> str:
        return "escalate" if state["decision"] is Decision.UNCERTAIN else "bundle"

    def _build(self) -> StateGraph:
        builder = StateGraph(PlannerState)
        builder.add_node("load", self._load)
        builder.add_node("dependencies", self._dependencies)
        builder.add_node("readiness", self._readiness)
        builder.add_node("decide", self._decide)
        builder.add_node("bundle", self._bundle)
        builder.add_node("evidence", self._evidence)
        builder.add_node("compose", self._compose)
        builder.add_node("escalate", self._escalate)

        builder.add_edge(START, "load")
        builder.add_edge("load", "dependencies")
        builder.add_edge("dependencies", "readiness")
        builder.add_edge("readiness", "decide")
        builder.add_conditional_edges(
            "decide",
            self._route_after_decide,
            {"bundle": "bundle", "escalate": "escalate"},
        )
        builder.add_edge("bundle", "evidence")
        builder.add_edge("evidence", "compose")
        builder.add_edge("compose", END)
        # An uncertain plan still gets written to the ledger and still tells the
        # family there is no date yet — silence is its own harm.
        builder.add_edge("escalate", "evidence")
        return builder

    # ---------------- entry point ----------------

    def plan_visit(
        self,
        patient: Patient,
        steps: list[CareStep],
        target_kind: StepKind,
        today: date | None = None,
        compose: bool = True,
    ) -> PlannerState:
        initial: PlannerState = {
            "patient": patient,
            "steps": steps,
            "target_kind": target_kind,
            "today": today or date.today(),
            "compose": compose,
        }
        started = perf_counter()
        result = self._compiled.invoke(initial)
        result["plan_ms"] = (perf_counter() - started) * 1000
        return result


def _rationale(state: PlannerState) -> str:
    """One-line English explanation for the navigator console."""
    decision = state.get("decision")
    if decision is Decision.GO:
        n = len(state.get("bundled_step_ids", ()))
        if n:
            return f"all prerequisites satisfied; {n + 1} steps bundled into one trip"
        return "all prerequisites satisfied; single-step visit"
    if decision is Decision.WAIT:
        names = ", ".join(b.kind.value for b in state.get("blockers", ()))
        return f"waiting on: {names}"
    if state.get("missing_kinds"):
        names = ", ".join(k.value for k in sorted(state["missing_kinds"], key=lambda k: k.value))
        return f"no record for prerequisite(s): {names}; no date promised"
    return state.get("escalation") or "insufficient calibrated evidence; no date promised"
