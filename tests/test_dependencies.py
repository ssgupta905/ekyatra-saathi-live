from __future__ import annotations

import pytest
from saathi.domain.enums import StepKind
from saathi.graph.dependencies import CycleError, InMemoryDependencyGraph


@pytest.fixture
def graph():
    return InMemoryDependencyGraph()


def test_review_consult_requires_both_reports(graph):
    prereqs = graph.prerequisites(StepKind.REVIEW_CONSULT)
    assert StepKind.PATHOLOGY_REPORT in prereqs
    assert StepKind.RADIOLOGY_REPORT in prereqs


def test_transitive_prerequisites_reach_the_first_consult(graph):
    ancestors = graph.transitive_prerequisites(StepKind.REVIEW_CONSULT)
    assert StepKind.BIOPSY in ancestors
    assert StepKind.SCAN in ancestors
    assert StepKind.CONSULT in ancestors


def test_treatment_depends_on_everything_before_it(graph):
    ancestors = graph.transitive_prerequisites(StepKind.TREATMENT)
    assert StepKind.REVIEW_CONSULT in ancestors
    assert StepKind.PATHOLOGY_REPORT in ancestors


def test_consult_and_biopsy_share_a_trip(graph):
    """The bundling that turns the deck's four trips into two."""
    assert graph.can_share_trip(StepKind.CONSULT, StepKind.BIOPSY)
    assert graph.can_share_trip(StepKind.BIOPSY, StepKind.CONSULT)


def test_a_step_cannot_share_a_trip_with_itself(graph):
    assert not graph.can_share_trip(StepKind.SCAN, StepKind.SCAN)


def test_dependent_steps_do_not_share_a_trip_by_default(graph):
    #  A review consult cannot happen on the same trip as the biopsy that
    #  feeds it — the report will not exist yet.
    assert not graph.can_share_trip(StepKind.BIOPSY, StepKind.REVIEW_CONSULT)


def test_cyclic_edges_are_rejected():
    with pytest.raises(CycleError):
        InMemoryDependencyGraph(
            edges=[
                (StepKind.CONSULT, StepKind.SCAN),
                (StepKind.SCAN, StepKind.CONSULT),
            ]
        )
