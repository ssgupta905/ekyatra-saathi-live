"""One family's situation as a graph, assembled from records that exist.

A knowledge graph is the easiest thing in a demo to fake and the hardest to
tell apart from a faked one, so the rule here is narrow and absolute: **every
node is something this system is holding, and every edge is a relationship it
can point at.** Nothing is drawn because it would complete the picture. A
family with no pending order has no pending-order node; a disruption nobody
has answered has no approval edge; a graph with four nodes in it is the right
graph when there are four things.

That is why this reads state rather than taking a description. The caller
passes a patient id and this goes and looks: at the hospital snapshot the
connector holds, at the questions the conversation has open, at the readings
waiting on a navigator, at the plan the planner last produced. If a thing is
not in one of those, it does not appear.

**What the edges are for.** The interesting claim in any of these journeys is
not "here is a patient" — it is *why this date and not another*, and that is a
path: a leave that collides with a visit, a constraint the family stated, a
slot that satisfies both. Reading the path is the explanation. So edges carry
a verb, and the verbs are few and literal — `conflicts_with`, `constraint`,
`satisfies`, `blocks`, `approved_by` — rather than a vocabulary invented to
look sophisticated.

**What is deliberately absent.** No clinical nodes. Not a diagnosis, not a
result, not what a report said. The same boundary `ports/hospital.py` draws at
the seam is drawn again here, because a graph is exactly where somebody would
be tempted to add "and the biopsy showed…" to make it look complete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class Node:
    """One thing that exists, with the record it came from."""

    id: str
    #: What kind of thing. Used for colour and shape, never for logic.
    kind: str
    label: str
    #: A second line: a date, a figure, a status. Short enough to render.
    detail: str = ""
    #: Where this came from, so a reader can go and check it. "OpenEMR
    #: calendar", "the family, by voice", "our planner" — the provenance is
    #: the point of showing a graph at all rather than a sentence.
    source: str = ""

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "detail": self.detail,
            "source": self.source,
        }


@dataclass(frozen=True)
class Edge:
    """A relationship this system can point at."""

    source: str
    target: str
    verb: str

    def to_json(self) -> dict:
        return {"from": self.source, "to": self.target, "verb": self.verb}


@dataclass
class Graph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def add(self, node: Node) -> str:
        """Add a node unless it is already there, and return its id."""
        if not any(existing.id == node.id for existing in self.nodes):
            self.nodes.append(node)
        return node.id

    def link(self, source: str, target: str, verb: str) -> None:
        """Join two nodes, but only if both are really in the graph.

        The guard that keeps this honest. An edge to a node that was never
        added is a relationship to something that does not exist, and drawing
        it would be the exact failure this module is written to avoid.
        """
        known = {node.id for node in self.nodes}
        if source not in known or target not in known:
            return
        already = any(
            e.source == source and e.target == target and e.verb == verb for e in self.edges
        )
        if not already:
            self.edges.append(Edge(source, target, verb))

    def to_json(self) -> dict:
        return {
            "nodes": [node.to_json() for node in self.nodes],
            "edges": [edge.to_json() for edge in self.edges],
        }


def _day(moment: datetime | date | None) -> str:
    if moment is None:
        return ""
    return moment.strftime("%d %b") if hasattr(moment, "strftime") else str(moment)


def _connector_for(runner: Any, patient_id: str) -> Any | None:
    """The hospital connector that knows this family, if one does."""
    syncs = getattr(runner, "hospital_syncs", None) or {}
    for sync in syncs.values():
        snapshot = getattr(sync, "snapshot", None)
        for appointment in getattr(snapshot, "by_ref", {}).values():
            if sync.links.patient_for(appointment) == patient_id:
                return sync
    # No appointment matched, but a single connected hospital is still the
    # right place to read orders and leave from.
    return next(iter(syncs.values()), None)


def build(runner: Any, patient_id: str) -> Graph:
    """Everything this system holds about one family, as a graph.

    Reads live state. Each block below is guarded by whether the thing is
    actually there, which is why the function is mostly `if` — that shape is
    the honesty, not clutter to be tidied away.
    """
    graph = Graph()
    world = runner.world
    patient = world.patient(patient_id)
    if patient is None:
        return graph

    family = graph.add(
        Node(
            id=f"patient:{patient_id}",
            kind="patient",
            label=patient.name or patient_id,
            detail=f"{patient.home_district} · {patient.home_distance_km:.0f} km",
            source="our records",
        )
    )

    # ---- what the hospital holds for them ----
    # The runner keeps one connector per hospital. Pick the one that can
    # actually match this family rather than assuming there is only ever one
    # — a pilot with two hospitals would otherwise draw an empty graph for
    # every family at the second.
    sync = _connector_for(runner, patient_id)
    snapshot = getattr(sync, "snapshot", None)
    appointments = list(getattr(snapshot, "by_ref", {}).values()) if snapshot else []
    theirs = [
        appointment
        for appointment in appointments
        if sync and sync.links.patient_for(appointment) == patient_id
    ]
    for appointment in theirs:
        visit = graph.add(
            Node(
                id=f"visit:{appointment.ref}",
                kind="visit",
                label=appointment.service_name or "Appointment",
                detail=f"{_day(appointment.starts_at)} {appointment.starts_at:%H:%M}"
                f" · {appointment.state.value}",
                source="OpenEMR calendar",
            )
        )
        graph.link(family, visit, "has_visit")

    # ---- a provider away, and what it collides with ----
    for leave in getattr(sync, "recent", []) if sync else []:
        if leave.get("kind") != "leave" or leave.get("patient_id") != patient_id:
            continue
        away = graph.add(
            Node(
                id=f"leave:{leave.get('at', '')}",
                kind="leave",
                label="Provider away",
                detail=leave.get("summary", "")[:80],
                source="OpenEMR calendar",
            )
        )
        # Only the visit the leave actually covers. Linking every open visit
        # drew a conflict with an appointment a week later that the leave does
        # not touch — an edge that is simply untrue, which is the one thing a
        # graph must never contain.
        on = leave.get("day", "")
        for appointment in theirs:
            if not appointment.state.is_open:
                continue
            if on and appointment.starts_at.date().isoformat() != on:
                continue
            graph.link(f"visit:{appointment.ref}", away, "conflicts_with")

    # ---- anything still outstanding that a visit waits on ----
    orders = getattr(getattr(sync, "orders", None), "orders", {}) if sync else {}
    for order in orders.values():
        if sync and sync._patient_for_ref(order.patient_ref) != patient_id:
            continue
        pending = graph.add(
            Node(
                id=f"order:{order.ref}",
                kind="order",
                label=order.name or "Order",
                detail=order.state.value,
                source="OpenEMR orders",
            )
        )
        graph.link(family, pending, "has_pending")
        if order.state.blocks_dependents:
            for appointment in theirs:
                if appointment.state.is_open:
                    graph.link(pending, f"visit:{appointment.ref}", "blocks")

    # ---- what Saathi asked, and what the family said ----
    conversation = getattr(runner, "conversation", None)
    for question in getattr(conversation, "history", []) if conversation else []:
        if question.patient_id != patient_id:
            continue
        asked = graph.add(
            Node(
                id=f"question:{question.id}",
                kind="question",
                label="Saathi asked",
                detail=", ".join(topic.value for topic in question.topics),
                source=f"sent in {question.language.value}",
            )
        )
        graph.link(family, asked, "was_asked")

    for request in getattr(runner, "requests", {}).get(patient_id, []):
        said = graph.add(
            Node(
                id=f"request:{request.id}",
                kind="constraint",
                label=request.summary(),
                detail=(
                    "agreed by " + request.confirmed_by
                    if request.confirmed_by
                    else "waiting on a person"
                ),
                source="the family, in their own words",
            )
        )
        graph.link(family, said, "constraint")

        # Figures only when they can be traced to something she said. The
        # same rule the Console applies, applied again here, because a graph
        # is exactly where an unattributed number would look authoritative.
        travel = request.travel
        if travel.anything_said and request.travel_is_attributable:
            bits = []
            if travel.companions is not None:
                bits.append(f"{travel.companions} travelling with them")
            if travel.stated_cost_inr is not None:
                bits.append(f"they said about ₹{travel.stated_cost_inr}")
            if travel.refundable is not None:
                bits.append(
                    "booking can be changed"
                    if travel.refundable
                    else "booking cannot be changed"
                )
            if bits:
                money = graph.add(
                    Node(
                        id=f"travel:{request.id}",
                        kind="budget",
                        label=" · ".join(bits),
                        detail=travel.stated_in[:70],
                        source="the family, in their own words",
                    )
                )
                graph.link(said, money, "constraint")

    # ---- what the planner decided, and who agreed to it ----
    plan = getattr(runner, "plans", {}).get(patient_id)
    if plan is not None:
        decided = graph.add(
            Node(
                id=f"plan:{patient_id}",
                kind="plan",
                label=f"Plan: {plan.decision.value}",
                detail=_day(getattr(plan, "travel_on", None)) or "no date yet",
                source="our planner",
            )
        )
        graph.link(family, decided, "has_plan")
        for request in getattr(runner, "requests", {}).get(patient_id, []):
            if request.confirmed_by:
                graph.link(f"request:{request.id}", decided, "satisfies")
        for appointment in theirs:
            if appointment.state.is_open:
                graph.link(decided, f"visit:{appointment.ref}", "books")

    return graph


__all__ = ["Edge", "Graph", "Node", "build"]
