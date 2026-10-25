"""The hospital network's registries: hospitals, centres, clinicians, resources, accounts.

Read by every staff role, changed only by administrators, and every change is in
the ledger with the name of whoever made it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from saathi.adapters.records.sql import migrate
from saathi.adapters.registry import MemoryRegistryStore, SqlRegistryStore
from saathi.config import get_settings
from saathi.domain.enums import Role
from saathi.domain.registry import Clinician, Hospital, NetworkCentre
from saathi.main import create_app

PASSWORD = "password-123"


@pytest.fixture(params=["memory", "sql"])
def store(request, tmp_path):
    if request.param == "memory":
        return MemoryRegistryStore()
    url = f"sqlite:///{tmp_path}/reg.db"
    migrate(url)
    return SqlRegistryStore(url)


def test_a_registry_returns_what_it_was_given(store):
    store.save_hospital(Hospital(id="H1", name="One", place="Patna", departments=("radiology",)))
    store.save_centre(NetworkCentre(id="C1", hospital_id="H1", name="DC", place="Gaya",
                                    handles=("bloods",)))  # fmt: skip
    store.save_clinician(Clinician(id="D1", name="Dr A", hospital_id="H1", specialty="Oncology"))

    assert store.hospitals()[0].departments == ("radiology",)
    assert store.centres()[0].handles == ("bloods",)
    assert store.clinicians()[0].specialty == "Oncology"

    store.save_hospital(Hospital(id="H1", name="One renamed", place="Patna"))
    assert [h.name for h in store.hospitals()] == ["One renamed"]


def test_rules_are_versioned_never_overwritten(store):
    assert store.policy("H1") is None
    assert store.save_policy("H1", {"hospital_id": "H1"}, "Neha") == 1
    assert store.save_policy("H1", {"hospital_id": "H1", "reservation_lead_days": 5}, "Rohini") == 2

    policy, version, by = store.policy("H1")
    assert (version, by, policy["reservation_lead_days"]) == (2, "Rohini", 5)


# ---------------------------------------------------------------- the demo


@pytest.fixture
def demo():
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        yield client


def test_the_demo_registry_knows_the_hospitals_centres_and_doctors_of_its_stories(demo):
    hospitals = {h["id"]: h for h in demo.get("/api/registry/hospitals").json()}
    clinicians = [c["name"] for c in demo.get("/api/registry/clinicians").json()]
    centres = demo.get("/api/registry/centres").json()

    assert hospitals["TMH-MUM"]["name"].startswith("Tata Memorial")
    assert "Dr Amrita Sinha" in clinicians
    assert {c["place"] for c in centres} >= {"Darbhanga", "Gaya"}


def test_the_demo_lists_the_resources_a_desk_can_report(demo):
    ids = {r["id"] for r in demo.get("/api/resources").json()}
    assert "MRI-2" in ids


def test_staff_accounts_exist_only_where_login_is_on(demo):
    assert demo.get("/api/admin/users").status_code == 409


# ---------------------------------------------------------------- real records


@pytest.fixture
def real(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/real.db")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        identity = client.app.state.container.identity
        identity.add_user("neha", "Neha", Role.ADMIN, PASSWORD)
        identity.add_user("seema", "Seema Kamble", Role.NAVIGATOR, PASSWORD)
        yield client
    get_settings.cache_clear()


def as_(client, username):
    token = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    return {"authorization": f"Bearer {token.json()['token']}"}


def test_real_records_start_with_only_the_configured_hospitals(real):
    hospitals = real.get("/api/registry/hospitals", headers=as_(real, "seema")).json()
    assert {h["id"] for h in hospitals} == {"TMH-MUM", "HBCH-MZP"}
    assert all(h["name"] == h["id"] for h in hospitals), "no invented names"
    assert real.get("/api/registry/clinicians", headers=as_(real, "seema")).json() == []


def test_an_administrator_builds_the_network_and_the_ledger_says_who(real):
    admin = as_(real, "neha")
    hospital = {"id": "AIIMS-PAT", "name": "AIIMS Patna", "place": "Patna",
                "departments": ["radiology", "medical oncology"]}  # fmt: skip
    assert real.post("/api/registry/hospitals", json=hospital, headers=admin).status_code == 201
    centre = {"id": "dc-gaya", "hospital_id": "AIIMS-PAT", "name": "Gaya day care",
              "place": "Gaya", "handles": ["bloods", "maintenance_dose"]}  # fmt: skip
    assert real.post("/api/registry/centres", json=centre, headers=admin).status_code == 201
    doctor = {"id": "dr-rao", "name": "Dr P. Rao", "specialty": "Radiation oncology",
              "hospital_id": "AIIMS-PAT", "department": "radiation oncology"}  # fmt: skip
    assert real.post("/api/registry/clinicians", json=doctor, headers=admin).status_code == 201
    edited = real.patch("/api/registry/centres/dc-gaya", json={"kind": "hub"}, headers=admin)

    assert edited.json()["kind"] == "hub"
    entries = real.get("/api/ledger?source=navigator", headers=admin).json()["entries"]
    claims = [e["claim"] for e in entries if e["patient_id"] == "registry"]
    assert any("AIIMS-PAT added" in c for c in claims)
    assert any("centre dc-gaya changed: kind" in c for c in claims)
    entry = next(
        e for e in real.app.state.container.ledger.all_entries() if "dr-rao added" in e.claim
    )
    assert entry.metadata["by"] == "Neha"


def test_the_network_holds_together(real):
    admin = as_(real, "neha")
    orphan = {"id": "c9", "hospital_id": "NOPE", "name": "x", "place": "y"}
    assert real.post("/api/registry/centres", json=orphan, headers=admin).status_code == 422
    twice = {"id": "TMH-MUM", "name": "again", "place": "Mumbai"}
    assert real.post("/api/registry/hospitals", json=twice, headers=admin).status_code == 409
    bad_kind = {"id": "c8", "hospital_id": "TMH-MUM", "name": "x", "place": "y", "kind": "spa"}
    assert real.post("/api/registry/centres", json=bad_kind, headers=admin).status_code == 422


def test_staff_read_the_registry_but_only_administrators_change_it(real):
    nav = as_(real, "seema")
    assert real.get("/api/registry/hospitals", headers=nav).status_code == 200
    assert real.get("/api/resources", headers=nav).status_code == 200
    body = {"id": "X", "name": "X", "place": "X"}
    assert real.post("/api/registry/hospitals", json=body, headers=nav).status_code == 403
    rename = real.patch("/api/registry/hospitals/TMH-MUM", json={"name": "Y"}, headers=nav)
    assert rename.status_code == 403
    assert real.get("/api/admin/users", headers=nav).status_code == 403


def test_an_administrator_manages_staff_accounts(real):
    admin = as_(real, "neha")
    new = {"username": "imran", "name": "Imran Shaikh", "role": "desk", "password": PASSWORD}

    created = real.post("/api/admin/users", json=new, headers=admin)
    listed = real.get("/api/admin/users", headers=admin).json()

    assert created.status_code == 201
    assert "password_hash" not in created.json()
    assert {u["username"] for u in listed} == {"neha", "seema", "imran"}
    assert all("password" not in str(u.keys()) for u in listed)

    real.patch("/api/admin/users/imran", json={"active": False}, headers=admin)
    blocked = real.post("/api/auth/login", json={"username": "imran", "password": PASSWORD})
    assert blocked.status_code == 401, "a deactivated account cannot sign in"

    real.patch("/api/admin/users/imran", json={"active": True, "password": "a-new-password"},
               headers=admin)  # fmt: skip
    again = real.post("/api/auth/login", json={"username": "imran", "password": "a-new-password"})
    assert again.status_code == 200


def test_an_administrator_cannot_lock_themself_out(real):
    admin = as_(real, "neha")
    response = real.patch("/api/admin/users/neha", json={"active": False}, headers=admin)
    assert response.status_code == 422


def test_a_family_account_cannot_be_made_with_a_password(real):
    admin = as_(real, "neha")
    body = {"username": "fam", "name": "Family", "role": "caregiver", "password": PASSWORD}
    assert real.post("/api/admin/users", json=body, headers=admin).status_code == 422
