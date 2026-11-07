"""Configuration: each hospital's rules (versioned, audited, honestly not yet live),
what is switched on, and the audit log's filters."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from saathi.api.admin import _listens, _speaks
from saathi.config import get_settings
from saathi.domain.enums import Role
from saathi.main import create_app

PASSWORD = "password-123"


@pytest.fixture
def real(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/c.db")
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        identity = client.app.state.container.identity
        identity.add_user("neha", "Neha", Role.ADMIN, PASSWORD)
        identity.add_user("seema", "Seema", Role.NAVIGATOR, PASSWORD)
        yield client
    get_settings.cache_clear()


def as_(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    return {"authorization": f"Bearer {r.json()['token']}"}


def test_a_hospital_with_no_saved_rules_says_it_runs_on_built_in_behaviour(real):
    body = real.get("/api/admin/policy/TMH-MUM", headers=as_(real, "neha")).json()

    assert body["source"] == "default"
    assert body["version"] == 0
    assert body["used_by_planner"] is False
    assert "built-in behaviour" in body["note"]
    assert all(step["confirmed"] is False for step in body["policy"]["steps"].values())
    # It says exactly what the planner would read, and what it would not.
    assert any("bring" in item for item in body["read_by_planner"])
    assert any("slot times" in item for item in body["not_read_yet"])


def test_saved_rules_say_they_are_in_force(real):
    admin = as_(real, "neha")
    policy = real.get("/api/admin/policy/TMH-MUM", headers=admin).json()["policy"]

    saved = real.put("/api/admin/policy/TMH-MUM", json=policy, headers=admin).json()
    body = real.get("/api/admin/policy/TMH-MUM", headers=admin).json()

    assert saved["used_by_planner"] is True and body["used_by_planner"] is True
    assert "In force" in body["note"]


def test_saving_rules_makes_a_new_version_and_an_audit_row(real):
    admin = as_(real, "neha")
    policy = real.get("/api/admin/policy/TMH-MUM", headers=admin).json()["policy"]
    policy["reservation_lead_days"] = 5
    policy["steps"]["joint_clinic"]["weekdays"] = [2]
    policy["steps"]["joint_clinic"]["confirmed"] = True
    policy["requirements"] = {"review_consult": ["hospital_file", "ayushman"]}

    first = real.put("/api/admin/policy/TMH-MUM", json=policy, headers=admin).json()
    second = real.put("/api/admin/policy/TMH-MUM", json=policy, headers=admin).json()
    now = real.get("/api/admin/policy/TMH-MUM", headers=admin).json()

    assert (first["version"], second["version"]) == (1, 2)
    assert now["source"] == "saved" and now["saved_by"] == "Neha"
    assert now["policy"]["reservation_lead_days"] == 5
    assert now["policy"]["steps"]["joint_clinic"]["weekdays"] == [2]
    audit = real.get("/api/ledger?patient_id=registry", headers=admin).json()
    claims = [e["claim"] for e in audit["entries"]]
    assert "rules for TMH-MUM saved as version 2" in claims


@pytest.mark.parametrize(
    "change, why",
    [
        ({"reservation_lead_days": "soon"}, "integer"),
        ({"requirements": {"review_consult": ["a_passport"]}}, "unknown documents"),
        ({"requirements": {"teleport": ["hospital_file"]}}, "unknown step kinds"),
        ({"hospital_id": "HBCH-MZP"}, "different hospital"),
        ({"surprise": 1}, "extra"),
    ],
)
def test_bad_rules_are_refused_with_the_reason(real, change, why):
    admin = as_(real, "neha")
    policy = real.get("/api/admin/policy/TMH-MUM", headers=admin).json()["policy"]

    response = real.put("/api/admin/policy/TMH-MUM", json={**policy, **change}, headers=admin)

    assert response.status_code == 422
    assert why.split()[0] in str(response.json()["detail"]).lower()


def test_rules_are_for_administrators_and_known_hospitals(real):
    assert real.get("/api/admin/policy/TMH-MUM", headers=as_(real, "seema")).status_code == 403
    assert real.get("/api/admin/policy/NOWHERE", headers=as_(real, "neha")).status_code == 404


def test_integrations_say_what_is_on_without_leaking_anything(real, monkeypatch):
    body = real.get("/api/admin/integrations", headers=as_(real, "neha")).json()

    assert body["world"] == "real"
    assert body["login"]["on"] is True
    assert body["records_database"] == "sqlite"
    assert body["language_layer"] is None
    text = str(body)
    assert "dev-only" not in text and "password" not in text.lower()


def test_the_audit_log_filters_searches_and_pages_newest_first(real):
    admin = as_(real, "neha")
    for i in range(3):
        real.post("/api/registry/hospitals", headers=admin,
                  json={"id": f"H{i}", "name": f"Hospital {i}", "place": "Patna"})  # fmt: skip

    page = real.get("/api/ledger?q=hospital&limit=2", headers=admin).json()
    rest = real.get("/api/ledger?q=hospital&limit=2&offset=2", headers=admin).json()

    assert page["total"] == 3
    assert [e["source_record_id"] for e in page["entries"]] == ["hospital/H2", "hospital/H1"]
    assert [e["source_record_id"] for e in rest["entries"]] == ["hospital/H0"]
    assert page["entries"][0]["metadata"]["by"] == "Neha"


def test_speech_lists_who_is_asked_rather_than_who_answers(real, monkeypatch):
    """A key that is *set* is not a key that *works*.

    A deployment once ran for hours with a Sarvam key the service rejected.
    Listening fell through to Whisper and looked fine; speaking had nothing to
    fall through to and returned 502; and this page said "Sarvam" for both. The
    screen cannot know who answers, so it names everyone it would ask, in order,
    and says plainly when the list is empty.
    """
    body = real.get("/api/admin/integrations", headers=as_(real, "neha")).json()

    #: The suite runs with no credentials, so both lists are empty here — and an
    #: empty list is the honest answer, not a missing field.
    assert body["speech_to_text"] == []
    assert body["text_to_speech"] == []

    #: The order is the fallback order. Sarvam is asked first because it is the
    #: one that knows Odia; Groq is the second ear and has no mouth at all.
    both = SimpleNamespace(
        sarvam_api_key="s", groq_api_key="g",
        sarvam_listen_model="saarika:v2.5", sarvam_speak_model="bulbul:v3",
        whisper_model="whisper-large-v3-turbo",
    )  # fmt: skip
    assert [n.split(" ·")[0] for n in _listens(both)] == ["Sarvam", "Groq"]
    assert [n.split(" ·")[0] for n in _speaks(both)] == ["Sarvam"]

    #: With Groq alone the system can still listen but cannot speak, and an Odia
    #: family — whose language no browser voice has — hears nothing.
    ear_only = SimpleNamespace(**{**vars(both), "sarvam_api_key": ""})
    assert _listens(ear_only) and _speaks(ear_only) == []

    #: Model names, never the key itself.
    assert "s" not in str(_speaks(both)).replace("bulbul", "").replace("Sarvam", "")
