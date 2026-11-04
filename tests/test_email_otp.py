"""Signing in with a code sent to an email address."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from saathi.adapters.identity import BrevoEmailSender
from saathi.adapters.identity.email import mask
from saathi.adapters.records import SqlRecordStore
from saathi.bootstrap.container import build_container
from saathi.bootstrap.demo_records import apply_demo_contacts
from saathi.config import Settings, get_settings
from saathi.domain.enums import Role
from saathi.main import create_app

PASSWORD = "correct horse battery"
FAMILY = {
    "id": "P-EMAIL",
    "name": "Rai family",
    "home_district": "Gaya",
    "home_distance_km": 900,
    "language": "hi",
    "caregiver_phone": "+91 98000 11122",
    "caregiver_email": "Rai.Family@Gmail.com",
    "hospital_id": "TMH-MUM",
}


class Outbox:
    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    def send(self, email: str, code: str) -> None:
        self.codes[email] = code


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/email.db")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        container = client.app.state.container
        client.outbox = Outbox()
        container.identity._email_sender = client.outbox
        container.identity.add_user("imran", "Imran", Role.DESK, PASSWORD)
        token = client.post(
            "/api/auth/login", json={"username": "imran", "password": PASSWORD}
        ).json()["token"]
        registered = client.post(
            "/api/patients", json=FAMILY, headers={"authorization": f"Bearer {token}"}
        )
        assert registered.status_code == 201, registered.text
        yield client
    get_settings.cache_clear()


def test_a_code_sent_to_the_family_email_signs_them_in(api):
    api.post("/api/auth/otp/request", json={"email": "rai.family@gmail.com"})
    code = api.outbox.codes["rai.family@gmail.com"]

    response = api.post(
        "/api/auth/otp/verify", json={"email": "Rai.Family@gmail.com", "code": code}
    )

    assert response.status_code == 200
    principal = response.json()["principal"]
    assert principal["role"] == "caregiver"
    assert principal["patient_ids"] == ["P-EMAIL"]


def test_an_address_on_no_record_gets_the_same_answer_and_no_code(api):
    response = api.post("/api/auth/otp/request", json={"email": "stranger@example.com"})

    assert response.status_code == 202
    assert api.outbox.codes == {}


def test_a_wrong_code_does_not_sign_anyone_in(api):
    api.post("/api/auth/otp/request", json={"email": "rai.family@gmail.com"})

    response = api.post(
        "/api/auth/otp/verify", json={"email": "rai.family@gmail.com", "code": "000000"}
    )

    assert response.status_code == 401


def test_a_code_works_once(api):
    api.post("/api/auth/otp/request", json={"email": "rai.family@gmail.com"})
    code = api.outbox.codes["rai.family@gmail.com"]
    body = {"email": "rai.family@gmail.com", "code": code}

    assert api.post("/api/auth/otp/verify", json=body).status_code == 200
    assert api.post("/api/auth/otp/verify", json=body).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"phone": "9800011122", "email": "rai.family@gmail.com"},
        {"email": "not-an-address"},
    ],
)
def test_a_request_names_one_valid_way_to_be_reached(api, body):
    assert api.post("/api/auth/otp/request", json=body).status_code == 422


def test_the_phone_route_still_works(api):
    sent = {}
    api.app.state.container.identity._sender = type(
        "S", (), {"send": lambda self, phone, code: sent.update({phone: code})}
    )()

    api.post("/api/auth/otp/request", json={"phone": "+91 98000 11122"})
    verified = api.post(
        "/api/auth/otp/verify", json={"phone": "9800011122", "code": sent["9800011122"]}
    )

    assert verified.status_code == 200


def test_the_email_is_kept_across_a_restart(tmp_path):
    from saathi.domain.enums import Language
    from saathi.domain.models import Patient

    url = f"sqlite:///{tmp_path}/keep.db"
    SqlRecordStore(url).save_patient(
        Patient(
            id="P1", home_district="Gaya", home_distance_km=1.0, language=Language.HINDI,
            caregiver_phone="+919800011122", caregiver_email="a@b.co", hospital_id="TMH-MUM",
        )
    )

    assert SqlRecordStore(url).load().patients[0].caregiver_email == "a@b.co"


# ---------------------------------------------------------------- the provider


def _sender(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return BrevoEmailSender("key-123", "saathi@gmail.com", "Saathi", client=client)


def test_the_code_goes_to_brevo_over_https_with_the_key_in_a_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["api-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"messageId": "x"})

    _sender(handler).send("rai@gmail.com", "123456")

    assert seen["url"] == "https://api.brevo.com/v3/smtp/email"
    assert seen["key"] == "key-123"
    assert seen["body"]["to"] == [{"email": "rai@gmail.com"}]
    assert seen["body"]["sender"] == {"email": "saathi@gmail.com", "name": "Saathi"}
    assert "123456" in seen["body"]["textContent"]


def test_a_refusal_or_an_outage_is_swallowed_not_raised():
    _sender(lambda r: httpx.Response(401, json={"message": "Key not found"})).send("a@b.co", "1")

    def down(request):
        raise httpx.ConnectError("no route")

    _sender(down).send("a@b.co", "1")


def test_an_address_is_masked_in_logs():
    assert mask("rai.family@gmail.com") == "r***@gmail.com"


# ---------------------------------------------------------------- the demo contact


def _real(tmp_path, **over) -> Settings:
    return Settings(_env_file=None, world="real", records_url=f"sqlite:///{tmp_path}/d.db", **over)


def test_the_demo_email_signs_in_with_the_fixed_code(tmp_path):
    state = build_container(
        _real(
            tmp_path, seed_demo=True, seed_demo_email="Me@Gmail.com", demo_otp="246810",
        )
    )

    state.identity.request_email_otp("me@gmail.com")

    principal = state.identity.verify_email_otp("ME@gmail.com", "246810")
    assert principal is not None and principal.patient_ids == ("P0000",)


def test_an_email_added_later_reaches_a_database_seeded_before(tmp_path):
    first = _real(tmp_path, seed_demo=True)
    build_container(first)
    store = SqlRecordStore(first.records_url)

    assert apply_demo_contacts(store, _real(tmp_path, seed_demo_email="me@gmail.com")) is True
    assert apply_demo_contacts(store, _real(tmp_path, seed_demo_email="me@gmail.com")) is False
    assert next(p for p in store.load().patients if p.id == "P0000").caregiver_email == (
        "me@gmail.com"
    )
