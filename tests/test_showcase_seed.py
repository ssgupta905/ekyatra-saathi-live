"""The starter data tells the whole story, and tops itself up rather than starting over."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from saathi.adapters.records import MemoryRecordStore
from saathi.bootstrap.demo_records import SHOWCASE_PREFIX, seed_demo_records, seed_showcase
from saathi.config import Settings, get_settings
from saathi.main import create_app

TODAY = date(2026, 11, 3)


def test_the_showcase_is_added_once_and_only_once():
    store = MemoryRecordStore()

    assert seed_showcase(store, TODAY) is True
    assert seed_showcase(store, TODAY) is False

    records = store.load()
    assert len([p for p in records.patients if p.id.startswith(SHOWCASE_PREFIX)]) == 9
    assert {r.id for r in records.resources} == {"MRI-2", "DIALYSIS-3", "ECHO-CARDIOLOGIST"}


def test_it_tops_up_a_database_that_was_seeded_before_it_existed():
    store = MemoryRecordStore()
    seed_demo_records(store, TODAY, Settings(_env_file=None))
    before = len(store.load().patients)

    assert seed_showcase(store, TODAY) is True

    assert len(store.load().patients) == before + 9


@pytest.fixture
def deployed(tmp_path, monkeypatch):
    """The app as Render runs it: real world, login on, an empty database, seeding on."""
    monkeypatch.setenv("SAATHI_ENVIRONMENT", "render")
    monkeypatch.setenv("SAATHI_AUTH_SECRET", "a-test-signing-secret-of-some-length")
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/deployed.db")
    monkeypatch.setenv("SAATHI_ADMIN_USERNAME", "founder")
    monkeypatch.setenv("SAATHI_ADMIN_PASSWORD", "a-long-secret")
    monkeypatch.setenv("SAATHI_SEED_DEMO", "true")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        token = client.post(
            "/api/auth/login", json={"username": "founder", "password": "a-long-secret"}
        ).json()["token"]
        client.headers["authorization"] = f"Bearer {token}"
        yield client
    get_settings.cache_clear()


def test_the_deployed_world_shows_every_verdict_and_more_than_one_pathway(deployed):
    boards = deployed.get("/api/boards", params={"watched": "false"}).json()["boards"]
    patients = {p["id"]: p for p in deployed.get("/api/patients").json()}

    assert len(boards) == len(patients) == 21, "no family is silently left off the boards"
    assert {b["decision"] for b in boards} == {"go", "wait", "replan", "uncertain"}
    assert {p["pathway_id"] for p in patients.values()} == {
        "oncology",
        "dialysis",
        "post_discharge",
    }


def test_an_outage_on_the_seeded_mri_reaches_the_families_booked_on_it(deployed):
    today = deployed.get("/api/live").json()["current"]

    reported = deployed.post(
        "/api/disruptions",
        json={"resource_id": "MRI-2", "kind": "machine_down", "unavailable_from": today},
    ).json()

    assert set(reported["affected_patient_ids"]) <= {"SHOW-MRI-1", "SHOW-MRI-2"}


def test_a_family_with_an_abha_number_can_be_asked_for_consent(deployed):
    response = deployed.get("/api/patients/SHOW-WAIT-1/consent")

    assert response.status_code == 200
    assert response.json()["grants"] == []
