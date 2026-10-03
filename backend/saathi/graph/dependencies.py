"""The dependency graph: what each visit needs before it is worth travelling for.

The graph is a DAG over `StepKind`. An edge A -> B means "B requires A".
`InMemoryDependencyGraph` is the reference implementation and the one the tests
and the synthetic demo run against; `Neo4jDependencyGraph` is the same interface
backed by the pilot's Neo4j instance.

The rule this module exists to enforce: a travel step is never proposed while
any of its prerequisites is unsatisfied.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Protocol

from ..domain.enums import ResourceKind, StepKind

#: Default clinical-logistics DAG for a solid-tumour pathway. Edges are
#: logistical ordering, not clinical advice: they say which step's *output*
#: must exist before another step is worth a journey.
DEFAULT_EDGES: tuple[tuple[StepKind, StepKind], ...] = (
    (StepKind.CONSULT, StepKind.BIOPSY),
    (StepKind.CONSULT, StepKind.BLOODS),
    (StepKind.CONSULT, StepKind.SCAN),
    (StepKind.BIOPSY, StepKind.PATHOLOGY_REPORT),
    (StepKind.SCAN, StepKind.RADIOLOGY_REPORT),
    #: The doctor's sketch: the PET-CT follows the MRI and its report, and the
    #: joint clinic cannot sit before the PET-CT it exists to discuss.
    (StepKind.RADIOLOGY_REPORT, StepKind.PET_CT),
    (StepKind.PET_CT, StepKind.JOINT_CLINIC),
    (StepKind.REVIEW_CONSULT, StepKind.JOINT_CLINIC),
    (StepKind.PATHOLOGY_REPORT, StepKind.REVIEW_CONSULT),
    (StepKind.RADIOLOGY_REPORT, StepKind.REVIEW_CONSULT),
    (StepKind.BLOODS, StepKind.REVIEW_CONSULT),
    #: Back on the spine via the review consult, not the joint clinic: the
    #: joint clinic is a leaf. Putting it between the review and treatment
    #: would make every patient in the cohort — none of whom have one on
    #: record — fail `missing_prerequisite_kinds` and go UNCERTAIN.
    (StepKind.REVIEW_CONSULT, StepKind.TREATMENT),
    #: Maintenance is a single repeating `StepKind`; the 21-day recurrence and
    #: the per-dose echo gate are computed by `planner.tools`, not by edges.
    (StepKind.TREATMENT, StepKind.MAINTENANCE_DOSE),
)

#: Steps that can share a trip when both are due. Ordered pairs are symmetric.
CO_LOCATABLE: tuple[frozenset[StepKind], ...] = (
    frozenset({StepKind.CONSULT, StepKind.BIOPSY}),
    frozenset({StepKind.CONSULT, StepKind.BLOODS}),
    frozenset({StepKind.BIOPSY, StepKind.BLOODS}),
    frozenset({StepKind.SCAN, StepKind.REVIEW_CONSULT}),
    #: The pair the brief's option B turns on: the MRI at 8 am and the PET-CT
    #: at 2 pm the same afternoon, one visit instead of two.
    frozenset({StepKind.SCAN, StepKind.PET_CT}),
    frozenset({StepKind.REVIEW_CONSULT, StepKind.JOINT_CLINIC}),
    frozenset({StepKind.BLOODS, StepKind.REVIEW_CONSULT}),
    frozenset({StepKind.MAINTENANCE_DOSE, StepKind.ECHO_REVIEW}),
)

#: Which kind of bookable resource a step needs, for matching a disruption
#: (resource down for a window) to the patients it affects. Steps with no
#: entry here don't book against a trackable resource.
RESOURCE_REQUIREMENTS: dict[StepKind, ResourceKind] = {
    StepKind.SCAN: ResourceKind.MACHINE,
    StepKind.ECHO_REVIEW: ResourceKind.STAFF,
    StepKind.MAINTENANCE_DOSE: ResourceKind.SUPPLY,
}


class CycleError(ValueError):
    """Raised when the configured edges do not form a DAG."""


class DependencyGraph(Protocol):
    def prerequisites(self, kind: StepKind) -> frozenset[StepKind]:
        """Direct prerequisites of `kind`."""

    def transitive_prerequisites(self, kind: StepKind) -> frozenset[StepKind]:
        """All ancestors of `kind`."""

    def can_share_trip(self, a: StepKind, b: StepKind) -> bool:
        """True when both steps can be done in one visit."""


class InMemoryDependencyGraph:
    """A small DAG held in process. No external service required."""

    def __init__(
        self,
        edges: Iterable[tuple[StepKind, StepKind]] = DEFAULT_EDGES,
        co_locatable: Iterable[frozenset[StepKind]] = CO_LOCATABLE,
    ) -> None:
        self._parents: dict[StepKind, set[StepKind]] = defaultdict(set)
        self._children: dict[StepKind, set[StepKind]] = defaultdict(set)
        for parent, child in edges:
            self._parents[child].add(parent)
            self._children[parent].add(child)
        self._co_locatable = tuple(co_locatable)
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        # Kahn's algorithm; if any node is left with unmet parents there is a cycle.
        nodes = set(self._parents) | set(self._children)
        indegree = {n: len(self._parents.get(n, ())) for n in nodes}
        queue = [n for n, d in indegree.items() if d == 0]
        seen = 0
        while queue:
            node = queue.pop()
            seen += 1
            for child in self._children.get(node, ()):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if seen != len(nodes):
            raise CycleError("dependency edges contain a cycle")

    def prerequisites(self, kind: StepKind) -> frozenset[StepKind]:
        return frozenset(self._parents.get(kind, ()))

    def transitive_prerequisites(self, kind: StepKind) -> frozenset[StepKind]:
        seen: set[StepKind] = set()
        stack = list(self._parents.get(kind, ()))
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(self._parents.get(node, ()))
        return frozenset(seen)

    def can_share_trip(self, a: StepKind, b: StepKind) -> bool:
        if a == b:
            return False
        # Never bundle a step with one of its own ancestors: the second step
        # depends on output the first has not produced yet.
        if b in self.transitive_prerequisites(a) or a in self.transitive_prerequisites(b):
            return frozenset({a, b}) in self._co_locatable
        return frozenset({a, b}) in self._co_locatable


class Neo4jDependencyGraph:
    """Neo4j-backed graph for the pilot.

    Same interface as `InMemoryDependencyGraph`. Kept thin on purpose: the graph
    is read-mostly, so every method is a single Cypher query. Schema lives in
    `schema.cypher`.
    """

    def __init__(self, driver, database: str = "neo4j") -> None:
        self._driver = driver
        self._database = database

    def _read(self, cypher: str, **params):
        with self._driver.session(database=self._database) as session:
            return list(session.run(cypher, **params))

    def prerequisites(self, kind: StepKind) -> frozenset[StepKind]:
        rows = self._read(
            "MATCH (p:Step)-[:REQUIRED_BY]->(c:Step {kind: $kind}) RETURN p.kind AS kind",
            kind=kind.value,
        )
        return frozenset(StepKind(r["kind"]) for r in rows)

    def transitive_prerequisites(self, kind: StepKind) -> frozenset[StepKind]:
        rows = self._read(
            "MATCH (p:Step)-[:REQUIRED_BY*]->(c:Step {kind: $kind}) RETURN DISTINCT p.kind AS kind",
            kind=kind.value,
        )
        return frozenset(StepKind(r["kind"]) for r in rows)

    def can_share_trip(self, a: StepKind, b: StepKind) -> bool:
        if a == b:
            return False
        rows = self._read(
            "MATCH (x:Step {kind: $a})-[:CO_LOCATABLE]-(y:Step {kind: $b}) RETURN count(*) AS n",
            a=a.value,
            b=b.value,
        )
        return bool(rows and rows[0]["n"] > 0)
