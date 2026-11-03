"""Real records: entered by people, kept across a restart, planned on at once.

The real world has no planted ground truth, no simulated clock and no actors, so
everything here is the product's own behaviour: what a desk types in is what the
planner reasons about, and what it learns from a release is kept.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from saathi.adapters.records import MemoryRecordStore, SqlRecordStore
from saathi.config import Settings, get_settings
from saathi.domain.enums import (
    Channel,
    FamilyMemberRole,
    Language,
    ResourceKind,
    StepKind,
    StepStatus,
)
from saathi.domain.models import CareStep, FamilyMember, Patient, Resource
from saathi.main import create_app
from saathi.ports.records import TurnaroundObservation

TODAY = date.today()

PATIENT = {
    "id": "P-TEST",
    "name": "Test Family",
    "home_district": "Darbhanga",
    "home_distance_km": 1850,
    "language": "hi",
    "caregiver_phone": "+919800000000",
    "hospital_id": "TMH-MUM",
    "plan_target": "review_consult",
}


def _patient() -> Patient:
    return Patient(
        id="P-1",
        name="A",
        abha_number="12-3456",
        home_district="Gaya",
        home_distance_km=1500,
        language=Language.BENGALI,
        caregiver_phone="+911",
        hospital_id="TMH-MUM",
        family_members=(
            FamilyMember(
                id="P-1-m1",
                patient_id="P-1",
                role=FamilyMemberRole.CAREGIVER_PRIMARY,
                name="B",
                phone="+912",
                preferred_channel=Channel.IVR,
                language=Language.HINDI,
            ),
        ),
    )


def _step(**kw) -> CareStep:
    base = dict(id="P-1-s1", patient_id="P-1", kind=StepKind.PATHOLOGY_REPORT,
                status=StepStatus.PENDING_RESULT, completed_on=TODAY, queue="pathology_report")
    return CareStep(**{**base, **kw})


# ---------------------------------------------------------------- the stores


@pytest.fixture(params=["memory", "sql"])
def store(request, tmp_path):
    if request.param == "memory":
        return MemoryRecordStore()
    return SqlRecordStore(f"sqlite:///{tmp_path}/records.db")


def test_a_store_returns_what_it_was_given(store):
    store.save_patient(_patient(), StepKind.JOINT_CLINIC)
    store.save_step(_step())
    store.save_resource(
        Resource(id="MRI-1", kind=ResourceKind.MACHINE, display_name="MRI 1",
                 hospital_id="TMH-MUM", department="radiology")
    )
    store.add_turnaround(TurnaroundObservation("pathology_report", 6.0, TODAY, "TMH-MUM"))

    records = store.load()

    assert records.patients == (_patient(),)
    assert records.steps["P-1"] == (_step(),)
    assert records.plan_targets == {"P-1": StepKind.JOINT_CLINIC}
    assert [r.id for r in records.resources] == ["MRI-1"]
    assert records.turnaround[0].days == 6.0


def test_saving_again_replaces_rather_than_duplicates(store):
    store.save_patient(_patient())
    moved = _patient().model_copy(update={"home_district": "Patna", "family_members": ()})
    store.save_patient(moved)
    store.save_step(_step())
    store.save_step(_step(status=StepStatus.RESULT_AVAILABLE, result_available_on=TODAY))

    records = store.load()

    assert len(records.patients) == 1
    assert records.patients[0].home_district == "Patna"
    assert records.patients[0].family_members == ()
    assert [s.status for s in records.steps["P-1"]] == [StepStatus.RESULT_AVAILABLE]


def test_a_sql_store_survives_being_reopened(tmp_path):
    url = f"sqlite:///{tmp_path}/r.db"
    first = SqlRecordStore(url)
    first.save_patient(_patient())
    first.close()

    assert SqlRecordStore(url).load().patients == (_patient(),)


# ---------------------------------------------------------------- the real world over HTTP


@pytest.fixture
def real_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    # These tests are about the records. Who may enter them is test_auth.py.
    monkeypatch.setenv("SAATHI_AUTH", "off")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/real.db")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def api(real_env):
    with TestClient(create_app()) as client:
        yield client


def _register(api, **over):
    response = api.post("/api/patients", json={**PATIENT, **over})
    assert response.status_code == 201, response.text
    return response.json()


def _plan(api, patient_id):
    return api.post("/api/plan", json={"patient_id": patient_id}).json()


def test_the_real_world_starts_empty_and_is_not_simulated(api):
    live = api.get("/api/live").json()

    assert live["world"] == "real"
    assert live["patients"] == 0
    assert live["running"] is True
    assert live["metrics"] == {}, "no ground truth, so no score"


def test_the_clock_cannot_be_driven_in_the_real_world(api):
    for action in ("pause", "step", "reset"):
        assert api.post("/api/live/control", json={"action": action}).status_code == 409


def test_registering_a_family_makes_them_visible_and_planned(api):
    _register(api)

    assert [p["id"] for p in api.get("/api/patients").json()] == ["P-TEST"]
    assert api.get("/api/live").json()["watched"] == ["P-TEST"]
    assert "P-TEST" in api.get("/api/boards").text


def test_a_family_can_be_put_on_another_pathway(api):
    assert {p["id"] for p in api.get("/api/pathways").json()} >= {"oncology", "dialysis"}

    registered = _register(api, pathway_id="dialysis")

    assert registered["pathway_id"] == "dialysis"
    board = api.get("/api/patients/P-TEST/board").json()
    assert board["patient"]["id"] == "P-TEST"


def test_an_unknown_pathway_is_refused_with_a_way_forward(api):
    response = api.post("/api/patients", json={**PATIENT, "pathway_id": "nope"})

    assert response.status_code == 422
    assert "/pathways" in response.json()["detail"]


def test_a_duplicate_patient_is_refused(api):
    _register(api)
    assert api.post("/api/patients", json=PATIENT).status_code == 409


def test_a_pending_report_without_a_queue_or_sample_date_is_explained(api):
    _register(api)
    bad = {"kind": "pathology_report", "status": "pending_result"}

    response = api.post("/api/patients/P-TEST/steps", json=bad)

    assert response.status_code == 422
    assert "queue" in response.json()["detail"]


def test_entering_a_report_says_when_there_is_no_forecast_for_it_yet(api):
    _register(api)

    response = api.post(
        "/api/patients/P-TEST/steps",
        json={"kind": "pathology_report", "status": "pending_result",
              "completed_on": TODAY.isoformat(), "queue": "pathology_report"},
    )

    assert response.status_code == 201
    forecast = response.json()["forecast"]
    assert forecast["calibrated"] is False
    assert "no reliable forecast" in forecast["note"]


def test_a_release_is_recorded_replans_the_family_and_teaches_the_forecast(api):
    _register(api)
    sampled = TODAY - timedelta(days=5)
    step = api.post(
        "/api/patients/P-TEST/steps",
        json={"id": "P-TEST-path", "kind": "pathology_report", "status": "pending_result",
              "completed_on": sampled.isoformat(), "queue": "pathology_report"},
    ).json()["step"]
    api.post(
        "/api/patients/P-TEST/steps",
        json={"id": "P-TEST-review", "kind": "review_consult", "status": "scheduled",
              "scheduled_for": (TODAY + timedelta(days=9)).isoformat(),
              "queue": "review_consult"},
    )
    before = api.get("/api/ledger/P-TEST").json()["entries"]

    released = api.post(f"/api/steps/{step['id']}/release", json={"by": "Imran"})

    assert released.status_code == 200
    assert released.json()["step"]["status"] == "result_available"
    steps = {s["id"]: s for s in api.get("/api/patients/P-TEST/steps").json()}
    assert steps["P-TEST-path"]["result_available_on"] == TODAY.isoformat()
    after = api.get("/api/ledger/P-TEST").json()["entries"]
    assert any(e["claim"] == "pathology_report is result_available" for e in after)
    assert not any(e["claim"] == "pathology_report is result_available" for e in before)
    assert api.get("/api/health").json()["ledger_intact"] is True
    # Releasing twice is harmless.
    assert api.post(f"/api/steps/{step['id']}/release").status_code == 200


def test_a_report_cannot_be_marked_available_by_a_plain_edit(api):
    _register(api)
    api.post("/api/patients/P-TEST/steps", json={
        "id": "P-TEST-path", "kind": "pathology_report", "status": "pending_result",
        "completed_on": TODAY.isoformat(), "queue": "pathology_report"})

    response = api.patch("/api/steps/P-TEST-path", json={"status": "result_available"})

    assert response.status_code == 422
    assert "release" in response.json()["detail"]


def test_only_a_report_can_be_released(api):
    _register(api)
    api.post("/api/patients/P-TEST/steps", json={
        "id": "P-TEST-consult", "kind": "consult", "status": "scheduled",
        "scheduled_for": TODAY.isoformat()})

    assert api.post("/api/steps/P-TEST-consult/release").status_code == 422
    assert api.post("/api/steps/nope/release").status_code == 404


def test_what_was_entered_survives_a_restart(real_env):
    with TestClient(create_app()) as first:
        _register(first)
        first.post("/api/patients/P-TEST/steps", json={
            "id": "P-TEST-path", "kind": "pathology_report", "status": "pending_result",
            "completed_on": (TODAY - timedelta(days=4)).isoformat(),
            "queue": "pathology_report"})
        first.post("/api/steps/P-TEST-path/release", json={"by": "Imran"})
        first.post("/api/patients/P-TEST/family", json={
            "name": "Sunita", "phone": "+919811111111", "language": "hi"})

    get_settings.cache_clear()
    with TestClient(create_app()) as second:
        patients = second.get("/api/patients").json()
        steps = second.get("/api/patients/P-TEST/steps").json()
        assert [p["id"] for p in patients] == ["P-TEST"]
        assert [m["name"] for m in patients[0]["family_members"]] == ["Sunita"]
        assert steps[0]["status"] == "result_available"
        assert second.get("/api/live").json()["watched"] == ["P-TEST"]


def test_a_restart_remembers_how_long_reports_take(real_env):
    with TestClient(create_app()) as first:
        _register(first)
        for i in range(3):
            first.post("/api/patients/P-TEST/steps", json={
                "id": f"P-TEST-r{i}", "kind": "radiology_report", "status": "pending_result",
                "completed_on": (TODAY - timedelta(days=3 + i)).isoformat(),
                "queue": "radiology_report"})
            first.post(f"/api/steps/P-TEST-r{i}/release")
        n_first = first.app.state.container.planner.predictor.n_calibration("radiology_report")

    get_settings.cache_clear()
    with TestClient(create_app()) as second:
        n_second = second.app.state.container.planner.predictor.n_calibration("radiology_report")

    assert n_first == n_second == 3


def test_the_audit_trail_survives_a_restart_and_still_verifies(real_env):
    with TestClient(create_app()) as first:
        _register(first)
        first.post("/api/patients/P-TEST/steps", json={
            "id": "P-TEST-path", "kind": "pathology_report", "status": "pending_result",
            "completed_on": (TODAY - timedelta(days=4)).isoformat(),
            "queue": "pathology_report"})
        first.post("/api/steps/P-TEST-path/release", json={"by": "Imran", "note": "ward called"})
        before = first.get("/api/ledger/P-TEST").json()["entries"]

    get_settings.cache_clear()
    with TestClient(create_app()) as second:
        ledger = second.get("/api/ledger/P-TEST").json()
        assert ledger["intact"] is True
        assert [e["entry_hash"] for e in ledger["entries"]] == [e["entry_hash"] for e in before]
        assert second.app.state.container.ledger.verify() is True
        # A new entry chains onto the restored head rather than forking it.
        second.post("/api/patients/P-TEST/steps", json={
            "id": "P-TEST-visit", "kind": "consult", "status": "scheduled",
            "scheduled_for": TODAY.isoformat()})
        assert second.app.state.container.ledger.verify() is True


def test_resources_can_be_registered(api):
    response = api.post("/api/resources", json={
        "id": "MRI-9", "kind": "machine", "display_name": "MRI 9",
        "hospital_id": "TMH-MUM", "department": "radiology"})
    assert response.status_code == 201


def test_the_demo_world_refuses_entered_records():
    get_settings.cache_clear()
    with TestClient(create_app()) as demo:
        response = demo.post("/api/patients", json=PATIENT)
    assert response.status_code == 409
    assert "real world" in response.json()["detail"]


def test_the_simulator_cannot_be_switched_on_over_real_records():
    with pytest.raises(ValueError, match="SAATHI_WORLD=real"):
        Settings(world="real", sim_mode=True)


# ---------------------------------------------------------------- CSV import

HEADER = (
    "record_type,id,patient_id,name,abha_number,home_district,home_distance_km,language,"
    "caregiver_phone,hospital_id,plan_target,kind,status,scheduled_for,completed_on,"
    "result_available_on,queue,resource_id,role,phone,channel\n"
)
CSV_OK = HEADER + (
    f"patient,P-CSV,,Csv Family,,Purnia,2000,or,+919822222222,TMH-MUM,review_consult,,,,,,,,,,\n"
    f"family,P-CSV-m1,P-CSV,Meera,,,,hi,,,,,,,,,,,caregiver_primary,+919833333333,whatsapp\n"
    f"step,P-CSV-path,P-CSV,,,,,,,,,pathology_report,pending_result,,{TODAY},,pathology_report,,,,\n"
    f"step,P-CSV-rev,P-CSV,,,,,,,,,review_consult,scheduled,"
    f"{TODAY + timedelta(days=8)},,,review_consult,,,,\n"
)


def _post_csv(api, text, commit=False):
    return api.post(f"/api/import/csv?commit={str(commit).lower()}", content=text,
                    headers={"content-type": "text/csv"})


def test_the_published_template_parses_clean(api):
    template = api.get("/api/import/template.csv").text
    body = _post_csv(api, template).json()
    assert body["errors"] == []
    assert body["counts"]["patients"] == 1


def test_a_csv_dry_run_writes_nothing(api):
    body = _post_csv(api, CSV_OK).json()

    assert body["counts"] == {
        "patients": 1, "family_members": 1, "steps": 2, "errors": 0, "skipped": 0,
    }
    assert body["committed"] is None
    assert api.get("/api/patients").json() == []


def test_a_committed_csv_creates_and_plans_the_family(api):
    body = _post_csv(api, CSV_OK, commit=True).json()

    assert body["committed"]["applied"] is True
    patient = api.get("/api/patients").json()[0]
    assert patient["id"] == "P-CSV"
    assert patient["family_members"][0]["name"] == "Meera"
    assert len(api.get("/api/patients/P-CSV/steps").json()) == 2


def test_one_bad_row_blocks_the_whole_file_and_says_which(api):
    broken = CSV_OK.replace(",or,", ",klingon,").replace("pending_result", "waiting")

    response = _post_csv(api, broken, commit=True)

    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert {e["where"] for e in errors} >= {"row 2", "row 4"}
    assert any("language" in e["message"] for e in errors)
    assert api.get("/api/patients").json() == [], "nothing is half-entered"


def test_a_csv_with_unknown_columns_is_refused_up_front(api):
    body = _post_csv(api, "record_type,diagnosis\npatient,cancer\n").json()
    assert body["errors"][0]["where"] == "header"
    assert "diagnosis" in body["errors"][0]["message"]


def test_a_step_for_a_patient_that_does_not_exist_is_an_error(api):
    text = HEADER + f"step,s1,P-NOPE,,,,,,,,,consult,scheduled,{TODAY},,,consult,,,,\n"
    body = _post_csv(api, text).json()
    assert "P-NOPE" in body["errors"][0]["message"]


# ---------------------------------------------------------------- FHIR import


def _bundle(**over):
    patient = {
        "resourceType": "Patient", "id": "fhir-1",
        "identifier": [{"system": "https://healthid.ndhm.gov.in", "value": "91-1234"}],
        "name": [{"text": "Fhir Family"}],
        "telecom": [{"system": "phone", "value": "+919844444444"}],
        "address": [{"district": "Nadia"}],
        "communication": [{"language": {"coding": [{"code": "bn"}]}}],
        "extension": [{"url": "https://ekyatra.org/fhir/home-distance-km", "valueDecimal": 1950}],
    }
    related = {
        "resourceType": "RelatedPerson", "id": "rp1", "patient": {"reference": "Patient/fhir-1"},
        "name": [{"text": "Rina"}], "relationship": [{"text": "Wife"}],
        "telecom": [{"system": "phone", "value": "+919855555555"}],
    }
    report = {
        "resourceType": "DiagnosticReport", "id": "rep1", "status": "final",
        "subject": {"reference": "Patient/fhir-1"},
        "effectiveDateTime": f"{TODAY - timedelta(days=6)}T09:00:00Z",
        "issued": f"{TODAY}T10:00:00Z",
        "code": {"text": "Histopathology"}, "performer": [{"display": "TMH Pathology"}],
        "conclusion": "SECRET FINDING", "presentedForm": [{"data": "SECRETPDF"}],
    }
    scan = {
        "resourceType": "Appointment", "id": "ap1", "status": "booked",
        "start": f"{TODAY + timedelta(days=3)}T10:00:00Z",
        "code": {"text": "MRI brain"},
        "participant": [{"actor": {"reference": "Patient/fhir-1"}}],
    }
    doctor = {
        "resourceType": "Appointment", "id": "ap2", "status": "booked",
        "start": f"{TODAY + timedelta(days=4)}T10:00:00Z",
        "code": {"text": "Doctor visit"},
        "participant": [{"actor": {"reference": "Patient/fhir-1"}}],
    }
    entries = over.get("entries", [patient, related, report, scan, doctor])
    return {"resourceType": "Bundle", "entry": [{"resource": r} for r in entries]}


def _post_fhir(api, bundle, commit=False, **params):
    params = {"hospital_id": "TMH-MUM", "commit": str(commit).lower(), **params}
    return api.post("/api/import/fhir", params=params, json=bundle)


def test_fhir_import_reads_status_and_dates_and_never_content(api):
    body = _post_fhir(api, _bundle(), commit=True).json()

    assert body["errors"] == []
    steps = {s["id"]: s for s in api.get("/api/patients/fhir-1/steps").json()}
    assert steps["DiagnosticReport/rep1"]["status"] == "result_available"
    everything = json.dumps([api.get("/api/patients").json(), list(steps.values()),
                             api.get("/api/ledger/fhir-1").json()])
    assert "SECRET" not in everything


def test_a_released_fhir_report_is_ledgered_and_teaches_the_forecast(api):
    _post_fhir(api, _bundle(), commit=True)
    container = api.app.state.container

    assert container.planner.predictor.n_calibration("pathology_report:tmh pathology") == 1
    entries = api.get("/api/ledger/fhir-1").json()["entries"]
    assert any(e["claim"].endswith("result_available") for e in entries)


def test_fhir_maps_family_language_and_abha(api):
    _post_fhir(api, _bundle(), commit=True)
    patient = api.get("/api/patients").json()[0]

    assert patient["language"] == "bn"
    assert patient["abha_number"] == "91-1234"
    assert patient["family_members"][0]["name"] == "Rina"
    assert patient["family_members"][0]["role"] == "caregiver_primary"


def test_an_mri_appointment_is_a_scan_and_a_doctor_visit_is_not_a_ct(api):
    body = _post_fhir(api, _bundle(), commit=True).json()
    steps = {s["id"]: s["kind"] for s in api.get("/api/patients/fhir-1/steps").json()}

    assert steps["Appointment/ap1"] == "scan"
    assert "Appointment/ap2" not in steps, "'Doctor visit' must not be read as a CT"
    assert any(s["where"] == "Appointment/ap2" for s in body["skipped"])


def test_a_fhir_patient_with_no_distance_is_an_error_not_a_zero(api):
    bundle = _bundle()
    del bundle["entry"][0]["resource"]["extension"]

    body = _post_fhir(api, bundle).json()
    assert "home distance" in body["errors"][0]["message"]
    assert _post_fhir(api, bundle, default_distance_km=1900).json()["errors"] == []


def test_fhir_dry_run_writes_nothing(api):
    _post_fhir(api, _bundle())
    assert api.get("/api/patients").json() == []
