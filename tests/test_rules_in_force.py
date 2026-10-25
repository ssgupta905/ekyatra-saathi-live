"""A hospital's saved rules change what the planner does; no saved rules change nothing.

Shambhu's story makes the point: the MRI fails on a Thursday and is back on
Saturday. With no rules the scan simply moves to Saturday. Under the hospital's
rules the scan runs only on weekdays, the PET-CT must follow it by two days, and
the consultants meet on Tuesdays and Fridays, so the whole chain moves, and the
options say why.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from saathi.config import get_settings
from saathi.domain.enums import DisruptionKind, SourceSystem, StepKind
from saathi.domain.models import Disruption
from saathi.domain.policy import HospitalPolicy, StepPolicy, default_policy
from saathi.graph.dependencies import InMemoryDependencyGraph
from saathi.main import create_app
from saathi.planner import options as options_module
from saathi.planner import tools as planner_tools
from saathi.readiness.conformal import ConformalReadinessPredictor
from saathi.synthetic.scripted import MRI_2, SHAMBHU_ID, seed_shambhu_prasad

START = date(2026, 11, 12)  # a Thursday


def _mri_down(days: int) -> Disruption:
    return Disruption(
        id="d1", resource_id=MRI_2, kind=DisruptionKind.MACHINE_DOWN,
        raised_by=SourceSystem.HOSPITAL_FEED, raised_at="2026-11-12T08:00:00Z",
        unavailable_from=START, unavailable_to=START + timedelta(days=days - 1),
    )  # fmt: skip


def _weekday_scans() -> HospitalPolicy:
    base = default_policy("TMH-MUM")
    steps = dict(base.steps)
    steps[StepKind.SCAN.value] = steps[StepKind.SCAN.value].model_copy(
        update={"weekdays": (0, 1, 2, 3, 4)}
    )
    return base.model_copy(update={"steps": steps})


def _dates(steps) -> dict[StepKind, date]:
    return {s.kind: s.scheduled_for for s in steps if s.scheduled_for}


@pytest.fixture
def shambhu():
    patient, steps, _ = seed_shambhu_prasad(START)
    return patient, list(steps)


def test_with_no_saved_rules_the_options_are_exactly_as_before(shambhu):
    patient, steps = shambhu
    args = (patient, steps, _mri_down(2), StepKind.JOINT_CLINIC,
            InMemoryDependencyGraph(), ConformalReadinessPredictor(), START)  # fmt: skip

    assert options_module.enumerate_candidates(*args) == options_module.enumerate_candidates(
        *args, policy=None, round_trip_hours=40.0
    )


def test_saved_rules_move_each_step_onto_a_day_it_actually_runs(shambhu):
    _, steps = shambhu
    affected = {f"{SHAMBHU_ID}-scan"}
    resume = START + timedelta(days=2)  # Saturday
    graph = InMemoryDependencyGraph()

    plain = _dates(options_module._moved(steps, affected, resume, graph, START, None))
    ruled = _dates(options_module._moved(steps, affected, resume, graph, START, _weekday_scans()))

    assert plain[StepKind.SCAN] == date(2026, 11, 14), "no rules: the scan just moves to Saturday"
    assert plain[StepKind.JOINT_CLINIC] == date(2026, 11, 20)
    assert ruled[StepKind.SCAN] == date(2026, 11, 16), "weekdays only: Monday"
    assert ruled[StepKind.PET_CT] == date(2026, 11, 18), "two days after the scan"
    # Three days after the PET-CT is Saturday the 21st; the consultants next meet Tuesday.
    assert ruled[StepKind.JOINT_CLINIC] == date(2026, 11, 24)


def test_options_say_when_the_hospitals_rules_shaped_them(shambhu):
    patient, steps = shambhu
    options = options_module.enumerate_candidates(
        patient, steps, _mri_down(2), StepKind.JOINT_CLINIC, InMemoryDependencyGraph(),
        ConformalReadinessPredictor(), START, policy=_weekday_scans(), round_trip_hours=40.0,
    )

    assert options
    assert all("TMH-MUM's saved rules" in o.rationale for o in options)
    assert all("provisional" in o.rationale for o in options), "unconfirmed rules are flagged"


def test_a_journey_needing_more_notice_than_the_hospital_allows_is_counted(shambhu):
    patient, steps = shambhu
    strict = _weekday_scans().model_copy(update={"reservation_lead_days": 7})
    common = (patient, steps, _mri_down(2), StepKind.JOINT_CLINIC,
              InMemoryDependencyGraph(), ConformalReadinessPredictor(), START)  # fmt: skip

    plain = options_module.enumerate_candidates(*common, round_trip_hours=40.0)
    ruled = options_module.enumerate_candidates(*common, policy=strict, round_trip_hours=40.0)

    assert all(o.short_notice_journeys == 0 for o in plain)
    assert any(o.short_notice_journeys > 0 for o in ruled)


def test_whether_to_split_a_stay_follows_the_familys_own_journey(shambhu):
    patient, steps = shambhu
    common = (patient, steps, _mri_down(6), StepKind.JOINT_CLINIC,
              InMemoryDependencyGraph(), ConformalReadinessPredictor(), START)  # fmt: skip
    rules = HospitalPolicy(hospital_id="TMH-MUM", steps={
        StepKind.SCAN.value: StepPolicy(kind=StepKind.SCAN)})  # fmt: skip

    built_in = options_module.enumerate_candidates(*common)
    far = options_module.enumerate_candidates(*common, policy=rules, round_trip_hours=40.0)

    assert any(o.extra_trips == 2 for o in built_in), "a fixed 3-day threshold offers going home"
    # Forty hours each way: waiting ten days in the city still beats making the trip twice.
    assert not any(o.extra_trips == 2 for o in far)


def test_documents_a_hospital_asks_for_join_the_list_once():
    target = next(s for s in seed_shambhu_prasad(START)[1] if s.kind is StepKind.JOINT_CLINIC)

    plain = planner_tools.documents_to_bring(target, ())
    asked = planner_tools.documents_to_bring(
        target, (), {"joint_clinic": ["ayushman", "hospital_file", "blocks_slides"]}
    )

    assert "Ayushman Bharat card" not in plain
    assert "Ayushman Bharat card" in asked
    assert "Outside biopsy blocks or slides" in asked
    assert sum("patient id card" in d.lower() for d in asked) == 1, "asked for once, not twice"


# ---------------------------------------------------------------- end to end


@pytest.fixture
def demo():
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        yield client


def test_saving_rules_changes_what_families_are_told_to_bring_at_once(demo):
    container = demo.app.state.container
    plans = container.runner.plans
    go = next(
        (pid for pid, run in plans.items()
         if run.plan and run.plan.decision.value == "go"
         and container.world.patient(pid).hospital_id == "TMH-MUM"),
        None,
    )  # fmt: skip
    assert go, "the demo cohort has a family travelling to TMH-MUM"
    target_kind = container.world.step(plans[go].plan.target_step_id).kind.value
    assert container.planner.rules_for("TMH-MUM") is None

    rules = demo.get("/api/admin/policy/TMH-MUM").json()["policy"]
    rules["requirements"] = {target_kind: ["ayushman", "demand_draft"]}
    demo.put("/api/admin/policy/TMH-MUM", json=rules)

    after = container.runner.plans[go].plan.what_to_bring
    assert "Ayushman Bharat card" in after
    assert "Demand draft for the pathology fee" in after
    # Another hospital's families are untouched.
    assert container.planner.rules_for("HBCH-MZP") is None
