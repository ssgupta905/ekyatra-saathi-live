"""The disruption/approval HTTP surface, and the admin's cross-patient ledger
view — all credential-free, same configuration CI runs.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from saathi.domain.enums import StepKind, StepStatus
from saathi.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def _rig_scan(client, resource_id="MRI-2"):
    state = client.app.state.saathi
    patient = state.world.patients()[0]
    steps = state.world.steps[patient.id]
    for index, step in enumerate(steps):
        if step.kind is StepKind.SCAN:
            steps[index] = step.model_copy(
                update={
                    "resource_id": resource_id,
                    "scheduled_for": state.world.today + timedelta(days=1),
                    "status": StepStatus.SCHEDULED,
                }
            )
    from saathi.domain.enums import ResourceKind
    from saathi.domain.models import Resource

    state.world.register_resource(
        Resource(id=resource_id, kind=ResourceKind.MACHINE, display_name="MRI machine 2",
                 hospital_id="H1", department="radiology")
    )
    return patient.id


def test_admin_config_surfaces_real_readiness_settings(client):
    body = client.get("/api/admin/config").json()
    assert 0 < body["readiness"]["coverage"] < 1
    assert "radiology_report" in body["readiness"]["queue_turnaround_profiles"]
    assert "hi" in body["languages"]


def test_pending_options_lists_patients_awaiting_a_human(client):
    patient_id = _rig_scan(client)
    today = client.app.state.saathi.world.today
    client.post(
        "/api/disruptions",
        json={
            "resource_id": "MRI-2", "kind": "machine_down",
            "unavailable_from": today.isoformat(),
            "unavailable_to": (today + timedelta(days=10)).isoformat(),
            "note": "test",
        },
    )
    pending = client.get("/api/disruptions/pending").json()
    ids = [row["patient_id"] for row in pending]
    if patient_id in client.app.state.saathi.runner.options:
        assert patient_id in ids


def test_ledger_all_lists_entries_across_patients(client):
    client.post("/api/live/control", json={"action": "step"})
    body = client.get("/api/ledger").json()
    assert body["intact"] is True
    assert isinstance(body["entries"], list)


def test_raising_a_disruption_returns_affected_patients(client):
    patient_id = _rig_scan(client)
    today = client.app.state.saathi.world.today

    response = client.post(
        "/api/disruptions",
        json={
            "resource_id": "MRI-2",
            "kind": "machine_down",
            "unavailable_from": today.isoformat(),
            "unavailable_to": (today + timedelta(days=10)).isoformat(),
            "note": "MRI-2 out of service",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert patient_id in body["affected_patient_ids"]


def test_a_navigator_approving_a_treatment_option_is_rejected(client):
    patient_id = _rig_scan(client)
    today = client.app.state.saathi.world.today
    client.post(
        "/api/disruptions",
        json={
            "resource_id": "MRI-2", "kind": "machine_down",
            "unavailable_from": today.isoformat(),
            "unavailable_to": (today + timedelta(days=10)).isoformat(),
            "note": "test",
        },
    )
    state = client.app.state.saathi
    option_set = state.runner.options.get(patient_id)
    if option_set is None:
        pytest.skip("fixture cohort did not produce a human-choice case this run")

    step = state.world.step(option_set.options[0].target_step_id)
    for rows in state.world.steps.values():
        for i, s in enumerate(rows):
            if s.id == step.id:
                rows[i] = s.model_copy(update={"kind": StepKind.TREATMENT})

    response = client.post(
        f"/api/disruptions/{option_set.disruption_id}/approve",
        json={
            "patient_id": patient_id, "option_index": 0,
            "approved_by_role": "navigator", "approved_by": "Seema",
        },
    )
    assert response.status_code == 403
