"""Consent over HTTP: ask, answer, withdraw, and the door that checks every time.

Login is on, as it is in the real world, so each test is also a statement about
who may do what. The registry's own rules are in `test_consent.py`; this is the
wiring: the routes, the access checks on them, and that consent outlives a restart.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from saathi.config import get_settings
from saathi.domain.enums import Role
from saathi.main import create_app

PASSWORD = "correct horse battery"
ABHA = "91-1234-5678-9012"


class Outbox:
    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    def send(self, phone: str, code: str) -> None:
        self.codes[phone] = code


def _patient(**over) -> dict:
    return {
        "id": "P-A", "name": "Anand family", "home_district": "Gaya",
        "home_distance_km": 1500, "language": "hi",
        "caregiver_phone": "+91 98000 11122", "hospital_id": "TMH-MUM",
        "abha_number": ABHA, **over,
    }


REQUEST = {
    "purpose": "record_movement", "requester_id": "HBCH-MZP",
    "requester_name": "Homi Bhabha Cancer Hospital, Muzaffarpur",
    "categories": ["molecular pathology"], "reason": "taking over care",
}
GRANT = {"granted_by": "Vikash Anand", "capacity": "nominee", "channel": "ivr"}
POINTER = {
    "id": "R-1", "care_context_id": "CC-9", "test_name": "BRCA1 germline panel",
    "category": "molecular pathology", "performed_on": "2026-03-04",
    "source_name": "Tata Memorial", "source_reference": "tmh/lab/778",
}
RESOLVE = {"requester_id": "HBCH-MZP", "purpose": "record_movement"}


def _open(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/consent.db")
    get_settings.cache_clear()
    client = TestClient(create_app())
    client.__enter__()
    container = client.app.state.container
    client.outbox = Outbox()
    container.identity._sender = client.outbox
    for username, role in (
        ("seema", Role.NAVIGATOR), ("amrita", Role.DOCTOR), ("neha", Role.ADMIN),
    ):
        try:
            container.identity.add_user(username, username.title(), role, PASSWORD)
        except Exception:  # noqa: BLE001 - already present after a reopen
            pass
    return client


@pytest.fixture
def api(tmp_path, monkeypatch):
    client = _open(tmp_path, monkeypatch)
    yield client
    client.__exit__(None, None, None)
    get_settings.cache_clear()


def sign_in(api, username: str) -> dict:
    response = api.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"authorization": f"Bearer {response.json()['token']}"}


def caregiver(api, phone="9800011122") -> dict:
    api.post("/api/auth/otp/request", json={"phone": phone})
    code = api.outbox.codes[phone[-10:]]
    response = api.post("/api/auth/otp/verify", json={"phone": phone, "code": code})
    assert response.status_code == 200, response.text
    return {"authorization": f"Bearer {response.json()['token']}"}


def _family(api, **over) -> None:
    response = api.post("/api/patients", json=_patient(**over), headers=sign_in(api, "neha"))
    assert response.status_code == 201, response.text


def _consent(api, patient="P-A") -> str:
    return f"/api/patients/{patient}/consent"


def _asked_and_indexed(api):
    staff = sign_in(api, "seema")
    _family(api)
    request = api.post(f"{_consent(api)}/requests", json=REQUEST, headers=staff)
    assert request.status_code == 201, request.text
    pointer = api.post(f"{_consent(api)}/records", json=POINTER, headers=staff)
    assert pointer.status_code == 201, pointer.text
    return staff, request.json()["id"]


# ---------------------------------------------------------------- the flow


def test_ask_answer_open_withdraw_and_be_refused_on_the_record(api):
    staff, request_id = _asked_and_indexed(api)
    family = caregiver(api)

    granted = api.post(f"{_consent(api)}/requests/{request_id}/grant", json=GRANT, headers=family)
    assert granted.status_code == 201, granted.text
    grant = granted.json()
    assert grant["capacity"] == "nominee" and grant["active"] is True

    opened = api.post(f"{_consent(api)}/records/R-1/resolve", json=RESOLVE, headers=staff)
    assert opened.status_code == 200
    assert opened.json()["outcome"] == "granted"

    revoked = api.post(
        f"{_consent(api)}/grants/{grant['id']}/revoke",
        json={"by": "Vikash Anand", "reason": "changed our minds"}, headers=family,
    )
    assert revoked.status_code == 200 and revoked.json()["active"] is False

    refused = api.post(f"{_consent(api)}/records/R-1/resolve", json=RESOLVE, headers=staff)
    assert refused.status_code == 403
    assert refused.json()["detail"]["outcome"] == "revoked"

    log = api.get(f"{_consent(api)}/access-log", headers=staff).json()
    assert [a["outcome"] for a in log] == ["revoked", "granted"], "refusals are logged too"
    assert api.get(f"{_consent(api)}/active", headers=staff).json() == []
    assert api.get("/api/health").json()["ledger_intact"] is True


def test_nothing_opens_before_anyone_answers(api):
    staff, _ = _asked_and_indexed(api)

    response = api.post(f"{_consent(api)}/records/R-1/resolve", json=RESOLVE, headers=staff)

    assert response.status_code == 403
    assert response.json()["detail"]["outcome"] == "no_consent"


def test_consent_for_one_requester_does_not_open_the_door_for_another(api):
    staff, request_id = _asked_and_indexed(api)
    api.post(
        f"{_consent(api)}/requests/{request_id}/grant", json=GRANT, headers=caregiver(api)
    )

    other = {**RESOLVE, "requester_id": "SOMEONE-ELSE"}
    response = api.post(f"{_consent(api)}/records/R-1/resolve", json=other, headers=staff)

    assert response.status_code == 403


def test_a_request_can_be_answered_only_once(api):
    _, request_id = _asked_and_indexed(api)
    family = caregiver(api)
    url = f"{_consent(api)}/requests/{request_id}/grant"

    assert api.post(url, json=GRANT, headers=family).status_code == 201
    assert api.post(url, json=GRANT, headers=family).status_code == 409


def test_a_request_must_name_what_it_needs(api):
    _family(api)

    response = api.post(
        f"{_consent(api)}/requests", json={**REQUEST, "categories": []},
        headers=sign_in(api, "seema"),
    )

    assert response.status_code == 422


def test_capacity_must_be_stated_not_assumed(api):
    _, request_id = _asked_and_indexed(api)
    body = {k: v for k, v in GRANT.items() if k != "capacity"}

    response = api.post(
        f"{_consent(api)}/requests/{request_id}/grant", json=body, headers=caregiver(api)
    )

    assert response.status_code == 422


def test_a_family_with_no_abha_number_has_nothing_to_consent_about(api):
    _family(api, abha_number=None)

    response = api.get(_consent(api), headers=sign_in(api, "seema"))

    assert response.status_code == 409
    assert "ABHA" in response.json()["detail"]


# ---------------------------------------------------------------- who may do what


def test_a_caregiver_cannot_see_or_answer_another_familys_consent(api):
    _, request_id = _asked_and_indexed(api)
    _family(api, id="P-B", name="Banerjee", caregiver_phone="+919811100000",
            abha_number="91-0000-1111-2222")
    stranger = caregiver(api, "9811100000")

    assert api.get(_consent(api, "P-A"), headers=stranger).status_code == 404
    answer = api.post(
        f"{_consent(api, 'P-A')}/requests/{request_id}/grant", json=GRANT, headers=stranger
    )
    assert answer.status_code == 404


def test_a_caregiver_cannot_ask_for_consent_on_anyones_behalf(api):
    _family(api)

    response = api.post(f"{_consent(api)}/requests", json=REQUEST, headers=caregiver(api))

    assert response.status_code == 403


def test_a_request_for_a_record_that_is_not_theirs_is_not_found(api):
    _asked_and_indexed(api)
    staff = sign_in(api, "seema")
    _family(api, id="P-B", name="Banerjee", caregiver_phone="+919811100000",
            abha_number="91-0000-1111-2222")

    response = api.post(f"{_consent(api, 'P-B')}/records/R-1/resolve", json=RESOLVE, headers=staff)

    assert response.status_code == 404


def test_a_navigator_is_not_told_which_panel_was_run_but_a_doctor_is(api):
    _asked_and_indexed(api)

    navigator = api.get(f"{_consent(api)}/records", headers=sign_in(api, "seema")).json()
    doctor = api.get(f"{_consent(api)}/records", headers=sign_in(api, "amrita")).json()

    assert navigator[0]["test_name"] is None and navigator[0]["redacted"] is True
    assert navigator[0]["category"] == "molecular pathology"
    assert doctor[0]["test_name"] == "BRCA1 germline panel"


# ---------------------------------------------------------------- a restart


def test_consent_and_its_refusals_survive_a_restart(tmp_path, monkeypatch):
    first = _open(tmp_path, monkeypatch)
    try:
        staff, request_id = _asked_and_indexed(first)
        grant = first.post(
            f"{_consent(first)}/requests/{request_id}/grant", json=GRANT,
            headers=caregiver(first),
        ).json()
        first.post(
            f"{_consent(first)}/grants/{grant['id']}/revoke",
            json={"by": "Vikash Anand"}, headers=caregiver(first),
        )
        first.post(f"{_consent(first)}/records/R-1/resolve", json=RESOLVE, headers=staff)
    finally:
        first.__exit__(None, None, None)

    second = _open(tmp_path, monkeypatch)
    try:
        staff = sign_in(second, "seema")
        log = second.get(f"{_consent(second)}/access-log", headers=staff).json()
        assert [a["outcome"] for a in log] == ["revoked"]
        assert second.get(f"{_consent(second)}/active", headers=staff).json() == []
        snapshot = second.get(_consent(second), headers=staff).json()
        assert snapshot["records"] == 1 and snapshot["refused"] == 1
        assert snapshot["grants"][0]["revoked_at"] is not None, "a withdrawal stays withdrawn"
        again = second.post(f"{_consent(second)}/records/R-1/resolve", json=RESOLVE, headers=staff)
        assert again.status_code == 403
    finally:
        second.__exit__(None, None, None)
        get_settings.cache_clear()
