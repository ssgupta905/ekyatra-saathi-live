"""The molecular register: a record that a test happened, never what it found.

Three things are worth failing a build over, and they are what this file
checks.

**It cannot hold a result.** The note field is the obvious place somebody
would type one, so a note that reads like a finding is refused.

**Consent is its own purpose.** A family who agreed to visit coordination has
not agreed to this, and a doctor reading the register must be told the
difference between "no consent" and "no tests" — those are opposite
conclusions, and conflating them is how a repeat panel gets ordered.

**Withdrawal deletes.** Not a flag, not a filter: the rows go.

The layering rule that keeps all of this out of the planner lives in
`test_architecture.py`, where it belongs.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from saathi.adapters.molecular.memory import InMemoryMolecularRegister
from saathi.config import get_settings
from saathi.domain.enums import Role
from saathi.domain.molecular import (
    MolecularReport,
    MolecularTest,
    ReportState,
    reads_like_a_result,
)
from saathi.main import create_app

PASSWORD = "correct horse battery"
ABHA = "91-1234-5678-9012"
PHONE = "+91 98000 11122"


class Outbox:
    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    def send(self, phone: str, code: str) -> None:
        self.codes[phone] = code


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/mol.db")
    get_settings.cache_clear()
    client = TestClient(create_app())
    client.__enter__()
    container = client.app.state.container
    client.outbox = Outbox()
    container.identity._sender = client.outbox
    for username, role in (
        ("seema", Role.NAVIGATOR),
        ("amrita", Role.DOCTOR),
        ("neha", Role.ADMIN),
        ("deepa", Role.DESK),
    ):
        try:
            container.identity.add_user(username, username.title(), role, PASSWORD)
        except Exception:  # noqa: BLE001 - already present
            pass
    yield client
    client.__exit__(None, None, None)
    get_settings.cache_clear()


def sign_in(api, username: str) -> dict:
    response = api.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"authorization": f"Bearer {response.json()['token']}"}


def caregiver(api, phone="9800011122") -> dict:
    api.post("/api/auth/otp/request", json={"phone": phone})
    code = api.outbox.codes[phone[-10:]]
    response = api.post(
        "/api/auth/otp/verify", json={"phone": phone, "code": code}
    )
    assert response.status_code == 200, response.text
    return {"authorization": f"Bearer {response.json()['token']}"}


def _family(api) -> None:
    body = {
        "id": "P-A", "name": "Anand family", "home_district": "Gaya",
        "home_distance_km": 1500, "language": "hi", "caregiver_phone": PHONE,
        "hospital_id": "TMH-MUM", "abha_number": ABHA,
    }
    created = api.post("/api/patients", json=body, headers=sign_in(api, "neha"))
    assert created.status_code == 201, created.text


def _consent_given(api) -> None:
    """Ask for the molecular purpose, and have the family agree to it."""
    staff = sign_in(api, "seema")
    asked = api.post(
        "/api/patients/P-A/consent/requests",
        json={
            "purpose": "molecular_records",
            "requester_id": "TMH-MUM",
            "requester_name": "Tata Memorial Hospital",
            "categories": ["molecular pathology"],
            "reason": "so a second centre need not repeat the panel",
        },
        headers=staff,
    )
    assert asked.status_code == 201, asked.text
    granted = api.post(
        f"/api/patients/P-A/consent/requests/{asked.json()['id']}/grant",
        json={"granted_by": "Vikash Anand", "capacity": "nominee", "channel": "ivr"},
        headers=caregiver(api),
    )
    assert granted.status_code == 201, granted.text


HELD = {
    "test": "targeted_panel",
    "state": "held",
    "lab_name": "Tata Memorial molecular pathology",
    "ordered_by_centre": "TMH Mumbai",
    "ordered_on": "2026-03-02",
    "reported_on": "2026-03-21",
    "document_ref": "tmh/lab/7781",
}


# ------------------------------------------------------- no results, ever


@pytest.mark.parametrize(
    "note",
    [
        "EGFR positive",
        "no mutation detected",
        "HER2 amplified on repeat",
        "variant of uncertain significance",
    ],
)
def test_a_note_that_reads_like_a_finding_is_refused(api, note):
    _family(api)
    _consent_given(api)
    refused = api.post(
        "/api/patients/P-A/molecular",
        json={**HELD, "note": note},
        headers=sign_in(api, "deepa"),
    )
    assert refused.status_code == 422, refused.text
    assert "not what it found" in refused.json()["detail"]


def test_an_ordinary_note_is_accepted(api):
    _family(api)
    _consent_given(api)
    saved = api.post(
        "/api/patients/P-A/molecular",
        json={**HELD, "note": "family holds the paper copy as well"},
        headers=sign_in(api, "deepa"),
    )
    assert saved.status_code == 201, saved.text
    assert "Targeted panel" in saved.json()["summary"]


def test_the_screen_names_the_word_that_tripped_it():
    assert reads_like_a_result("ALK fusion seen") == "alk"
    assert reads_like_a_result("report collected by the brother") is None


# ------------------------------------------------------------- consent


def test_without_consent_a_doctor_is_told_so_rather_than_shown_nothing(api):
    _family(api)
    seen = api.get("/api/patients/P-A/molecular", headers=sign_in(api, "amrita"))
    assert seen.status_code == 200, seen.text
    body = seen.json()
    # The distinction that matters: not "this patient has had no tests".
    assert body["consented"] is False and body["reports"] == []
    assert "not agreed" in body["why"]


def test_recording_without_consent_is_refused(api):
    _family(api)
    refused = api.post(
        "/api/patients/P-A/molecular", json=HELD, headers=sign_in(api, "deepa")
    )
    assert refused.status_code == 403, refused.text


def test_withdrawal_deletes_the_rows(api):
    _family(api)
    _consent_given(api)
    doctor = sign_in(api, "amrita")
    api.post("/api/patients/P-A/molecular", json=HELD, headers=sign_in(api, "deepa"))
    assert len(api.get("/api/patients/P-A/molecular", headers=doctor).json()["reports"]) == 1

    gone = api.delete("/api/patients/P-A/molecular", headers=doctor)
    assert gone.status_code == 200 and gone.json()["removed"] == 1
    assert api.get("/api/patients/P-A/molecular", headers=doctor).json()["reports"] == []
    # And the store itself, not just the view.
    assert api.app.state.container.molecular.for_patient("P-A") == ()


# --------------------------------------------------------------- who may


def test_a_navigator_may_not_read_the_register(api):
    _family(api)
    _consent_given(api)
    refused = api.get("/api/patients/P-A/molecular", headers=sign_in(api, "seema"))
    assert refused.status_code == 403, refused.text


def test_the_family_may_not_read_it_either(api):
    _family(api)
    _consent_given(api)
    refused = api.get("/api/patients/P-A/molecular", headers=caregiver(api))
    assert refused.status_code == 403, refused.text


def test_a_desk_may_write_but_not_read(api):
    _family(api)
    _consent_given(api)
    desk = sign_in(api, "deepa")
    assert api.post("/api/patients/P-A/molecular", json=HELD, headers=desk).status_code == 201
    assert api.get("/api/patients/P-A/molecular", headers=desk).status_code == 403


def test_an_unknown_patient_is_a_404(api):
    asked = api.get("/api/patients/nobody/molecular", headers=sign_in(api, "amrita"))
    assert asked.status_code == 404, asked.text


# ---------------------------------------------------- what it is good for


def test_the_count_that_matters_is_what_cannot_be_fetched(api):
    """A report nobody can reach is the thing that causes a repeat panel."""
    _family(api)
    _consent_given(api)
    desk, doctor = sign_in(api, "deepa"), sign_in(api, "amrita")
    api.post("/api/patients/P-A/molecular", json=HELD, headers=desk)
    api.post(
        "/api/patients/P-A/molecular",
        json={
            "test": "ihc", "state": "elsewhere", "lab_name": "a district lab",
            "ordered_on": "2025-11-04", "reported_on": "2025-11-18",
        },
        headers=desk,
    )
    api.post(
        "/api/patients/P-A/molecular",
        json={"test": "fish", "state": "awaited", "ordered_on": "2026-03-20"},
        headers=desk,
    )

    body = api.get("/api/patients/P-A/molecular", headers=doctor).json()
    assert body["not_reachable"] == 1, "awaited is not the same as unreachable"
    # Oldest first: read as a history, so the district IHC leads.
    assert [r["test"] for r in body["reports"]] == ["ihc", "targeted_panel", "fish"]
    assert "report not held here" in body["reports"][0]["summary"]
    assert body["reports"][2]["summary"].endswith("not back yet")


def test_held_needs_somewhere_to_point(api):
    _family(api)
    _consent_given(api)
    refused = api.post(
        "/api/patients/P-A/molecular",
        json={**HELD, "document_ref": ""},
        headers=sign_in(api, "deepa"),
    )
    assert refused.status_code == 422
    assert "elsewhere" in refused.json()["detail"]


def test_recording_one_goes_into_the_ledger(api):
    _family(api)
    _consent_given(api)
    api.post("/api/patients/P-A/molecular", json=HELD, headers=sign_in(api, "deepa"))
    claims = [e.claim for e in api.app.state.container.ledger.for_patient("P-A")]
    assert any("Targeted panel" in c for c in claims), claims
    assert api.get("/api/health").json()["ledger_intact"] is True


# --------------------------------------------------------------- the store


def _report(**over) -> MolecularReport:
    base = {
        "id": "m-1", "patient_id": "P-A", "test": MolecularTest.EXOME,
        "state": ReportState.AWAITED, "recorded_at": datetime.now(UTC),
    }
    return MolecularReport(**{**base, **over})


def test_the_store_replaces_rather_than_duplicates():
    store = InMemoryMolecularRegister()
    store.save(_report())
    store.save(_report(state=ReportState.ELSEWHERE))
    (only,) = store.for_patient("P-A")
    assert only.state is ReportState.ELSEWHERE


def test_forget_says_how_many_went():
    store = InMemoryMolecularRegister()
    store.save(_report())
    store.save(_report(id="m-2"))
    assert store.forget("P-A") == 2
    assert store.forget("P-A") == 0, "a second withdrawal is not an error"


def test_only_held_with_a_pointer_can_be_fetched():
    assert _report(state=ReportState.HELD, document_ref="tmh/1").can_be_fetched
    assert not _report(state=ReportState.HELD).can_be_fetched
    assert not _report(state=ReportState.ELSEWHERE, document_ref="tmh/1").can_be_fetched
