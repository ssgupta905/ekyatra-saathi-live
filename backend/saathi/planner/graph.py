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
from collections.abc import Callable, Sequence
from datetime import date
from time import perf_counter

from langgraph.graph import END, START, StateGraph

from ..domain.enums import Channel, Decision, StepKind
from ..domain.models import CareStep, Disruption, Patient, ReadinessItem, VisitPlan
from ..domain.pathway import DEFAULT_PATHWAY_ID, get_pathway
from ..domain.policy import HospitalPolicy
from ..graph.dependencies import DependencyGraph, InMemoryDependencyGraph
from ..ledger.evidence import InMemoryEvidenceLedger
from ..ports.language import LanguageLayer
from ..ports.ledger import EvidenceLedger
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
        ledger: EvidenceLedger | None = None,
        language_layer: LanguageLayer | None = None,
        rules_for: Callable[[str], HospitalPolicy | None] | None = None,
    ) -> None:
        #: The oncology graph, and the one a test injects. Other pathways get
        #: their own, built on first use and kept: see `graph_for`.
        self.graph = dependency_graph or InMemoryDependencyGraph()
        self._pathway_graphs: dict[str, DependencyGraph] = {}
        self.predictor = predictor or ConformalReadinessPredictor()
        self.ledger = ledger or InMemoryEvidenceLedger()
        #: Optional so the planner can be exercised without API credentials —
        #: the demo and the tests run the full decision path with it unset.
        self.language_layer = language_layer
        #: A hospital's saved rules, by hospital id, or None when it has saved
        #: none — in which case planning is exactly what it was before rules
        #: existed. Set by the composition root once the registry is built.
        self.rules_for: Callable[[str], HospitalPolicy | None] = rules_for or (lambda _: None)
        self._compiled = self._build().compile()

    def graph_for(self, patient: Patient) -> DependencyGraph:
        """The dependency graph of the patient's own pathway."""
        if patient.pathway_id == DEFAULT_PATHWAY_ID:
            return self.graph
        if patient.pathway_id not in self._pathway_graphs:
            self._pathway_graphs[patient.pathway_id] = InMemoryDependencyGraph.from_pathway(
                get_pathway(patient.pathway_id)
            )
        return self._pathway_graphs[patient.pathway_id]

    def _requirements(self, state: PlannerState) -> dict[str, list[str]] | None:
        rules = self.rules_for(state["patient"].hospital_id)
        return rules.requirements if rules else None

    # ---------------- nodes ----------------

    def _load(self, state: PlannerState) -> PlannerState:
        target = tools.find_step(state["steps"], state["target_kind"])
        return {"target": target}

    def _dependencies(self, state: PlannerState) -> PlannerState:
        target = state.get("target")
        if target is None:
            return {"blockers": (), "missing_kinds": frozenset()}
        unmet = tools.unmet_prerequisites(target, state["steps"], self.graph_for(state["patient"]))
        missing = tools.missing_prerequisite_kinds(
            target, state["steps"], self.graph_for(state["patient"])
        )
        return {
            "blockers": tools.describe_blockers(
                unmet, self.predictor, state.get("disruptions", ())
            ),
            "missing_kinds": missing,
        }

    def _readiness(self, state: PlannerState) -> PlannerState:
        # Blockers already carry their conformal windows from `describe_blockers`.
        # The other parties' answers are picked out here: the ones that gate this
        # visit, or the next one.
        target = state.get("target")
        if target is None:
            return {"items": ()}
        gated = {target.id, *(b.step_id for b in state.get("blockers", ()))}
        return {"items": tools.relevant_items(state.get("readiness_items", ()), gated)}

    def _decide(self, state: PlannerState) -> PlannerState:
        if state.get("target") is None:
            return {
                "decision": Decision.UNCERTAIN,
                "escalation": f"no {state['target_kind'].value} step on record",
            }
        decision = tools.decide_with_items(
            tools.decide(state["blockers"], state["missing_kinds"], state["today"]),
            state.get("items", ()),
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
            "bundled_step_ids": tools.bundle_steps(
                target, state["steps"], self.graph_for(state["patient"])
            )
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

        items = state.get("items", ())
        # Every party's answer is a fact the plan relies on, so it is ledgered
        # like any other: nothing reaches a family without a source.
        item_refs = tuple(
            self.ledger.record_once(
                patient_id=state["patient"].id,
                source=item.source,
                source_record_id=item.id,
                claim=f"{item.kind.value} ({item.party}) is {item.status.value}",
                metadata={
                    "ready_by": item.ready_by.isoformat() if item.ready_by else None,
                    "alternative_available": item.alternative_available,
                },
            ).ref()
            for item in items
        )
        refs = (*refs, *item_refs)

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
                tools.documents_to_bring(
                    target,
                    bundled_kinds,
                    self._requirements(state),
                    get_pathway(state["patient"].pathway_id),
                )
                if target and state["decision"] is Decision.GO
                else ()
            ),
            where_to_go_first=(
                tools.where_to_go_first(
                    target, bundled_kinds, get_pathway(state["patient"].pathway_id)
                )
                if target and state["decision"] is Decision.GO
                else None
            ),
            evidence=refs,
            rationale=_rationale(state),
            readiness_items=items,
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
        disruptions: Sequence[Disruption] = (),
        readiness_items: Sequence[ReadinessItem] = (),
    ) -> PlannerState:
        initial: PlannerState = {
            "patient": patient,
            "steps": steps,
            "target_kind": target_kind,
            "today": today or date.today(),
            "compose": compose,
            "disruptions": tuple(disruptions),
            "readiness_items": tuple(readiness_items),
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
        parties = ", ".join(
            f"{i.party} ({i.kind.value})"
            for i in state.get("items", ())
            if i.status.value in ("pending", "blocked")
        )
        return "waiting on: " + ", ".join(x for x in (names, parties) if x)
    if decision is Decision.REPLAN:
        parties = ", ".join(
            f"{i.party} ({i.kind.value})"
            for i in state.get("items", ())
            if i.status.value == "blocked"
        )
        return f"{parties} cannot go ahead and another way exists; staff to approve a new plan"
    if any(i.status.value == "unknown" for i in state.get("items", ())):
        parties = ", ".join(
            f"{i.party} ({i.kind.value})"
            for i in state["items"]
            if i.status.value == "unknown"
        )
        return f"no answer yet from: {parties}; no date promised"
    if state.get("missing_kinds"):
        names = ", ".join(k.value for k in sorted(state["missing_kinds"], key=lambda k: k.value))
        return f"no record for prerequisite(s): {names}; no date promised"
    return state.get("escalation") or "insufficient calibrated evidence; no date promised"
