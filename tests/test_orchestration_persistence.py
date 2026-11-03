"""What a restart must not lose: outages, parties' answers, pending options, approvals.

Plans are deliberately absent. The planner recomputes them from the records on
every start, so a stored copy could only ever disagree with the truth.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from saathi.adapters.records import MemoryRecordStore, SqlRecordStore
from saathi.bootstrap.container import build_container
from saathi.config import Settings, get_settings
from saathi.domain.enums import (
    Decision,
    DisruptionKind,
    Language,
    ReadinessKind,
    ReadinessStatus,
    ResourceKind,
    Role,
    SourceSystem,
    StepKind,
    StepStatus,
)
from saathi.domain.models import (
    ApprovalDecision,
    CareStep,
    Disruption,
    Patient,
    PlanOption,
    ReadinessItem,
    Resource,
)
from saathi.ports.records import StoredOptionSet

NOW = datetime(2026, 11, 3, 9, 30, tzinfo=UTC)


@pytest.fixture(params=["memory", "sql"])
def store(request, tmp_path):
    if request.param == "memory":
        return MemoryRecordStore()
    return SqlRecordStore(f"sqlite:///{tmp_path}/orchestration.db")


def _disruption() -> Disruption:
    return Disruption(
        id="D-1", resource_id="MRI-2", kind=DisruptionKind.MACHINE_DOWN,
        raised_by=SourceSystem.HOSPITAL_FEED, raised_at=NOW,
        unavailable_from=date(2026, 11, 3), unavailable_to=date(2026, 11, 13),
        note="MRI-2 out of service",
    )


def _item(**over) -> ReadinessItem:
    base = dict(
        id="P-1-transport", patient_id="P-1", kind=ReadinessKind.TRANSPORT, party="Uber",
        status=ReadinessStatus.BLOCKED, alternative_available=True,
        source=SourceSystem.PARTNER, ready_by=date(2026, 11, 5),
    )
    return ReadinessItem(**{**base, **over})


def _option() -> PlanOption:
    return PlanOption(
        patient_id="P-1", target_step_id="P-1-review", decision=Decision.GO,
        travel_on=date(2026, 11, 9), rationale="every prerequisite is satisfied",
        nights_added=1,
    )


def test_an_outage_comes_back_as_it_was_reported(store):
    store.save_disruption(_disruption())

    assert store.load().disruptions == (_disruption(),)


def test_a_partys_answer_is_replaced_not_duplicated(store):
    store.save_readiness_item(_item())
    store.save_readiness_item(_item(status=ReadinessStatus.READY))

    items = store.load().readiness_items

    assert [i.status for i in items] == [ReadinessStatus.READY]


def test_two_families_may_use_the_same_item_id(store):
    store.save_readiness_item(_item())
    store.save_readiness_item(_item(patient_id="P-2"))

    assert {i.patient_id for i in store.load().readiness_items} == {"P-1", "P-2"}


def test_a_cleared_answer_stays_cleared(store):
    store.save_readiness_item(_item())
    store.delete_readiness_item("P-1", "P-1-transport")
    store.delete_readiness_item("P-1", "never-existed")  # not an error

    assert store.load().readiness_items == ()


def test_pending_options_round_trip_and_one_set_per_family(store):
    first = StoredOptionSet("P-1", "D-1", (_option(),), NOW)
    second = StoredOptionSet("P-1", "D-2", (_option(), _option()), NOW + timedelta(hours=1))
    store.save_option_set(first)
    store.save_option_set(second)

    loaded = store.load().option_sets

    assert loaded == (second,)
    store.delete_option_set("P-1")
    assert store.load().option_sets == ()


def test_an_approval_is_kept_with_its_copy_of_the_option(store):
    approval = ApprovalDecision(
        id="A-1", patient_id="P-1", disruption_id="D-1", option_summary=_option(),
        approved_by_role=Role.NAVIGATOR, approved_by="Seema Kamble", approved_at=NOW,
    )
    store.add_approval(approval)
    store.add_approval(approval)  # append-only: the same id twice is one row

    assert store.load().approvals == (approval,)


# ---------------------------------------------------------------- a real restart


@pytest.fixture
def real_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_AUTH", "off")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/real.db")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _build():
    return build_container(Settings(_env_file=None))


def _enter_family(state) -> str:
    today = state.world.today
    state.world.add_patient(
        Patient(
            id="P-REAL", home_distance_km=900.0, home_district="Gaya",
            language=Language.HINDI, caregiver_phone="+919900000003", hospital_id="H1",
        )
    )
    def step(kind, status, **extra):
        return CareStep(
            id=f"P-REAL-{kind.value}", patient_id="P-REAL", kind=kind, status=status,
            queue=kind.value, **extra,
        )

    for s in (
        step(StepKind.CONSULT, StepStatus.COMPLETED, completed_on=today - timedelta(days=3)),
        step(StepKind.BLOODS, StepStatus.COMPLETED, completed_on=today - timedelta(days=3)),
        step(StepKind.BIOPSY, StepStatus.COMPLETED, completed_on=today - timedelta(days=3)),
        step(StepKind.PATHOLOGY_REPORT, StepStatus.RESULT_AVAILABLE,
             completed_on=today - timedelta(days=3),
             result_available_on=today - timedelta(days=1)),
        step(StepKind.SCAN, StepStatus.SCHEDULED, scheduled_for=today + timedelta(days=1),
             resource_id="MRI-2"),
        step(StepKind.RADIOLOGY_REPORT, StepStatus.NOT_SCHEDULED),
        step(StepKind.REVIEW_CONSULT, StepStatus.SCHEDULED,
             scheduled_for=today + timedelta(days=3)),
    ):
        state.world.add_step(s)
    state.world.register_resource(
        Resource(id="MRI-2", kind=ResourceKind.MACHINE, display_name="MRI machine 2",
                 hospital_id="H1", department="radiology")
    )
    return "P-REAL"


async def test_a_restart_keeps_outages_answers_options_and_approvals(real_env):
    first = _build()
    patient_id = _enter_family(first)
    today = first.world.today

    first.world.set_readiness_item(_item(patient_id=patient_id, id=f"{patient_id}-transport"))
    await first.runner.raise_disruption(
        resource_id="MRI-2", kind=DisruptionKind.MACHINE_DOWN,
        unavailable_from=today, unavailable_to=today + timedelta(days=10),
        note="MRI-2 out of service",
    )
    assert patient_id in first.runner.options, "the rig must produce a human-choice case"
    pending_disruption = first.runner.options[patient_id].disruption_id
    first.world.store.close()

    second = _build()
    second.runner.restore()

    assert [i.party for i in second.world.readiness_for(patient_id)] == ["Uber"]
    assert pending_disruption in second.world.disruptions
    assert second.runner.options[patient_id].disruption_id == pending_disruption
    assert second.world.pending_approval[patient_id] == pending_disruption

    approval = await second.runner.approve_option(
        patient_id=patient_id, option_index=0,
        approved_by_role=Role.DOCTOR, approved_by="Dr Rao",
    )
    second.world.store.close()

    third = _build()
    third.runner.restore()

    assert patient_id not in third.runner.options, "an approved set must not come back"
    assert patient_id not in third.world.pending_approval
    assert [a.id for a in third.runner.approvals] == [approval.id]
    third.world.store.close()
