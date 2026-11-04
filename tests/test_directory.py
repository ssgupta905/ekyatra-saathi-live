"""The network directory: who is in it, who may change it, and what the roles page says."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from saathi.adapters.registry import MemoryRegistryStore
from saathi.bootstrap.demo_directory import DEMO_DIRECTORY, seed_directory
from saathi.config import get_settings
from saathi.domain.directory import OrgType
from saathi.domain.enums import Role
from saathi.main import create_app

PASSWORD = "correct horse battery"


def test_the_demo_directory_covers_every_kind_of_organisation_and_its_links_resolve():
    ids = {o.id for o in DEMO_DIRECTORY}

    assert {o.type for o in DEMO_DIRECTORY} == set(OrgType)
    assert len(DEMO_DIRECTORY) >= 30
    for org in DEMO_DIRECTORY:
        assert org.alternate_id is None or org.alternate_id in ids, org.id
        assert set(org.linked_ids) <= ids, org.id


def test_seeding_fills_an_empty_directory_once():
    store = MemoryRegistryStore()

    assert seed_directory(store) is True
    assert seed_directory(store) is False
    assert len(store.organisations()) == len(DEMO_DIRECTORY)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/dir.db")
    monkeypatch.setenv("SAATHI_SEED_DEMO", "true")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        identity = client.app.state.container.identity
        for name, role in (("neha", Role.ADMIN), ("seema", Role.NAVIGATOR)):
            identity.add_user(name, name.title(), role, PASSWORD)

        def sign_in(who: str) -> None:
            token = client.post(
                "/api/auth/login", json={"username": who, "password": PASSWORD}
            ).json()["token"]
            client.headers["authorization"] = f"Bearer {token}"

        client.sign_in = sign_in
        yield client
    get_settings.cache_clear()


def test_every_staff_role_can_read_the_directory_and_filter_it(api):
    api.sign_in("seema")

    everything = api.get("/api/directory").json()
    cabs = api.get("/api/directory", params={"type": "cab"}).json()
    near_patna = api.get("/api/directory", params={"district": "Patna", "type": "hotel"}).json()

    assert len(everything) >= 30
    assert {o["type"] for o in cabs} == {"cab"}
    assert [o["id"] for o in near_patna] == ["ho-lodge-patna"]
    assert {t["id"] for t in api.get("/api/directory/types").json()} == {t.value for t in OrgType}


def test_only_an_administrator_changes_the_directory(api):
    new = {"id": "cab-new", "name": "New Cabs", "type": "cab"}

    api.sign_in("seema")
    assert api.post("/api/directory", json=new).status_code == 403

    api.sign_in("neha")
    assert api.post("/api/directory", json=new).status_code == 201
    assert api.post("/api/directory", json=new).status_code == 409


def test_a_link_to_an_unknown_organisation_is_refused(api):
    api.sign_in("neha")

    response = api.post(
        "/api/directory",
        json={"id": "ph-x", "name": "X", "type": "pharmacy", "alternate_id": "nobody"},
    )

    assert response.status_code == 422


def test_an_edit_changes_how_a_simulated_partner_answers(api):
    api.sign_in("neha")

    edited = api.patch("/api/directory/cab-uber", json={"answer": "cannot", "delay_seconds": 10})

    assert edited.status_code == 200
    assert edited.json()["answer"] == "cannot"
    assert api.get("/api/directory", params={"q": "uber"}).json()[0]["delay_seconds"] == 10


def test_the_roles_page_reads_the_real_access_rules(api):
    api.sign_in("neha")

    roles = {r["role"]: r for r in api.get("/api/admin/roles").json()}

    assert roles["admin"]["routes"] > roles["desk"]["routes"] > 0
    assert roles["caregiver"]["routes"] == 0, "families have no staff routes"
    assert roles["admin"]["accounts"] == 1
