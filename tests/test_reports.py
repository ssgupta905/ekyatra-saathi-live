"""Report status and timing: what the control centre's report tracker shows.

Status, dates, the calibrated window and who said a report landed. Never content.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from saathi.config import get_settings
from saathi.domain.enums import Role, StepStatus
from saathi.main import create_app
from saathi.planner.tools import readiness_for

TODAY = date.today()


@pytest.fixture
def demo():
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        yield client


def test_every_report_window_is_the_one_the_planner_uses(demo):
    container = demo.app.state.container
    body = demo.get("/api/reports").json()

    assert body["reports"], "the demo cohort has reports"
    for row in body["reports"]:
        step = container.world.step(row["step_id"])
        window = readiness_for(step, container.planner.predictor)
        assert row["window"] == (window.model_dump(mode="json") if window else None)


def test_a_report_says_where_it_stands_against_its_window(demo):
    rows = demo.get("/api/reports").json()["reports"]
    today = demo.get("/api/live").json()["current"]

    for row in rows:
        if row["status"] == "result_available":
            assert row["state"] == "released"
        elif row["window"] and row["window"]["calibrated"]:
            if today > row["window"]["latest"]:
                assert row["state"] == "overdue"
            elif today >= row["window"]["earliest"]:
                assert row["state"] == "due"
            else:
                assert row["state"] == "waiting"


def test_overdue_and_due_come_first(demo):
    states = [r["state"] for r in demo.get("/api/reports").json()["reports"]]
    order = ["overdue", "due", "no_forecast", "no_window", "waiting", "released", "cancelled"]
    assert states == sorted(states, key=order.index)


def test_reports_carry_no_content_fields(demo):
    row = demo.get("/api/reports").json()["reports"][0]
    assert not {"conclusion", "result", "finding", "content", "value"} & set(row)


def test_filters_narrow_the_list(demo):
    everything = demo.get("/api/reports").json()["reports"]
    pid = everything[0]["patient_id"]
    one = demo.get(f"/api/reports?patient_id={pid}").json()["reports"]
    radiology = demo.get("/api/reports?queue=radiology_report").json()["reports"]

    assert one and all(r["patient_id"] == pid for r in one)
    assert radiology and all(r["queue"] == "radiology_report" for r in radiology)


def test_queue_forecasts_report_their_calibration_and_kept_coverage(demo):
    body = demo.get("/api/readiness/queues").json()
    queues = {q["queue"]: q for q in body["queues"]}

    assert body["coverage_target"] == pytest.approx(0.9)
    assert queues["pathology_report"]["calibrated"] is True
    assert queues["pathology_report"]["observations"] >= body["min_calibration"]
    coverage = queues["radiology_report"]["observed_coverage"]
    assert coverage is None or 0 <= coverage <= 1


# ---------------------------------------------------------------- real records


@pytest.fixture
def real(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/r.db")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        identity = client.app.state.container.identity
        identity.add_user("imran", "Imran Shaikh", Role.DESK, "password-123")
        token = client.post(
            "/api/auth/login", json={"username": "imran", "password": "password-123"}
        ).json()["token"]
        client.headers["authorization"] = f"Bearer {token}"
        yield client
    get_settings.cache_clear()


def test_a_new_queue_says_it_has_no_forecast_and_a_release_says_who(real):
    real.post("/api/patients", json={
        "id": "P-R", "home_district": "Gaya", "home_distance_km": 1500, "language": "hi",
        "caregiver_phone": "+919800000001", "hospital_id": "TMH-MUM"})
    real.post("/api/patients/P-R/steps", json={
        "id": "S1", "kind": "pathology_report", "status": "pending_result",
        "completed_on": (TODAY - timedelta(days=3)).isoformat(), "queue": "pathology_report"})

    before = real.get("/api/reports").json()["reports"][0]
    assert before["state"] == "no_forecast"

    real.post("/api/steps/S1/release")
    after = real.get("/api/reports").json()["reports"][0]

    assert after["status"] == StepStatus.RESULT_AVAILABLE.value
    assert after["state"] == "released"
    assert after["turnaround_days"] == 3
    assert after["release"]["by"] == "Imran Shaikh"
    queue = real.get("/api/readiness/queues").json()["queues"][0]
    seen = (queue["queue"], queue["observations"], queue["calibrated"])
    assert seen == ("pathology_report", 1, False)


def test_reports_are_for_staff_only(real):
    assert real.get("/api/reports", headers={"authorization": "Bearer nope"}).status_code == 401
