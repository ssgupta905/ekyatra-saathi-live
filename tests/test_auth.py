"""Who may do what, and that a signed-in person cannot talk their way past it.

Login is on in the real world and off in the demo. Every test here runs with it
on, so each one is a statement about the real thing: the role a request carries
is the role that signed in, not the one a body claims.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from fastapi.testclient import TestClient
from saathi.adapters.identity import LocalIdentity
from saathi.api.live import stream
from saathi.bootstrap.container import build_container
from saathi.config import Settings, get_settings
from saathi.domain.enums import Role
from saathi.main import create_app
from starlette.requests import Request

PASSWORD = "correct horse battery"
TODAY = date.today()
PATIENT = {
    "id": "P-A",
    "name": "Anand family",
    "home_district": "Gaya",
    "home_distance_km": 1500,
    "language": "hi",
    "caregiver_phone": "+91 98000 11122",
    "hospital_id": "TMH-MUM",
}


class Outbox:
    """Stands in for the SMS provider: remembers the last code per phone."""

    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    def send(self, phone: str, code: str) -> None:
        self.codes[phone] = code


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/auth.db")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        container = client.app.state.container
        client.outbox = Outbox()
        container.identity._sender = client.outbox
        for username, role in (
            ("seema", Role.NAVIGATOR),
            ("imran", Role.DESK),
            ("amrita", Role.DOCTOR),
            ("neha", Role.ADMIN),
        ):
            container.identity.add_user(username, username.title(), role, PASSWORD)
        yield client
    get_settings.cache_clear()


def sign_in(api, username: str) -> dict:
    response = api.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"authorization": f"Bearer {response.json()['token']}"}


def caregiver(api, phone="9800011122") -> dict:
    api.post("/api/auth/otp/request", json={"phone": phone})
    code = api.outbox.codes["".join(c for c in phone if c.isdigit())[-10:]]
    response = api.post("/api/auth/otp/verify", json={"phone": phone, "code": code})
    assert response.status_code == 200, response.text
    return {"authorization": f"Bearer {response.json()['token']}"}


# ---------------------------------------------------------------- the front door


def test_login_is_required_in_the_real_world_and_not_in_the_demo(api):
    assert api.get("/api/auth/config").json()["required"] is True
    get_settings.cache_clear()
    with TestClient(create_app()) as demo:
        pass
    # (the demo is exercised by the rest of the suite, which sends no token)
    assert demo is not None


def test_the_demo_world_needs_no_login(monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "demo")
    get_settings.cache_clear()
    with TestClient(create_app()) as demo:
        assert demo.get("/api/auth/config").json()["required"] is False
        assert demo.get("/api/patients").status_code == 200
        attempt = {"username": "x", "password": "y"}
        assert demo.post("/api/auth/login", json=attempt).status_code == 404
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "path",
    ["/api/patients", "/api/live", "/api/alerts", "/api/metrics", "/api/boards",
     "/api/desk/queue", "/api/ledger", "/api/admin/config", "/api/disruptions/pending"],
)
def test_nothing_answers_without_a_token(api, path):
    assert api.get(path).status_code == 401


def test_the_front_door_stays_open(api):
    assert api.get("/api/health").status_code == 200
    assert api.get("/api/auth/config").status_code == 200


def test_a_wrong_password_and_an_unknown_user_look_the_same(api):
    wrong = api.post("/api/auth/login", json={"username": "seema", "password": "nope-nope"})
    unknown = api.post("/api/auth/login", json={"username": "nobody", "password": "nope-nope"})

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_repeated_failures_lock_the_account_for_a_minute(api):
    for _ in range(5):
        api.post("/api/auth/login", json={"username": "seema", "password": "wrong-wrong"})

    locked = api.post("/api/auth/login", json={"username": "seema", "password": PASSWORD})

    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0


def test_a_tampered_or_foreign_token_is_refused(api):
    token = sign_in(api, "seema")["authorization"].split()[1]
    forged = token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB")

    for bad in (f"Bearer {forged}", "Bearer nonsense"):
        assert api.get("/api/patients", headers={"authorization": bad}).status_code == 401


def test_an_expired_token_is_refused(tmp_path):
    identity = LocalIdentity(
        f"sqlite:///{tmp_path}/t.db", secret="x" * 40, phones=_NoPhones(), staff_ttl=-5
    )
    from saathi.adapters.records.sql import migrate

    migrate(f"sqlite:///{tmp_path}/t.db")
    identity.add_user("a", "A", Role.DESK, PASSWORD)
    principal = identity.login("a", PASSWORD)
    token, _ = identity.issue_token(principal)

    assert identity.verify_token(token) is None


class _NoPhones:
    def families_for(self, phone):
        return ()


def test_me_says_who_is_signed_in(api):
    me = api.get("/api/auth/me", headers=sign_in(api, "amrita")).json()
    assert (me["name"], me["role"]) == ("Amrita", "doctor")


# ---------------------------------------------------------------- roles


def test_each_role_may_do_its_own_work_and_not_another_roles(api):
    desk, nav, doc, admin = (sign_in(api, u) for u in ("imran", "seema", "amrita", "neha"))

    # Entering records: desk and navigator, not the doctor.
    assert api.post("/api/patients", json=PATIENT, headers=doc).status_code == 403
    assert api.post("/api/patients", json=PATIENT, headers=nav).status_code == 201

    # Releasing a report and importing are the desk's.
    step = {"id": "S1", "kind": "pathology_report", "status": "pending_result",
            "completed_on": TODAY.isoformat(), "queue": "pathology_report"}
    assert api.post("/api/patients/P-A/steps", json=step, headers=nav).status_code == 201
    assert api.post("/api/steps/S1/release", headers=nav).status_code == 403
    assert api.post("/api/steps/S1/release", headers=doc).status_code == 403
    assert api.post("/api/steps/S1/release", headers=desk).status_code == 200

    # The audit log and the configuration are the administrator's.
    assert api.get("/api/ledger", headers=desk).status_code == 403
    assert api.get("/api/ledger", headers=admin).status_code == 200
    assert api.get("/api/admin/config", headers=nav).status_code == 403
    assert api.get("/api/admin/config", headers=admin).status_code == 200

    # Reporting an outage is the desk's; the doctor may not.
    assert api.get("/api/desk/queue", headers=doc).status_code == 200
    body = {"text": "MRI-2 down till Saturday"}
    assert api.post("/api/disruptions/read", json=body, headers=doc).status_code == 403


def test_a_release_is_recorded_under_the_name_that_signed_in(api):
    nav, desk = sign_in(api, "seema"), sign_in(api, "imran")
    api.post("/api/patients", json=PATIENT, headers=nav)
    api.post("/api/patients/P-A/steps", headers=nav, json={
        "id": "S1", "kind": "pathology_report", "status": "pending_result",
        "completed_on": TODAY.isoformat(), "queue": "pathology_report"})

    api.post("/api/steps/S1/release", headers=desk, json={"by": "Someone Else"})

    ledger = api.get("/api/ledger/P-A", headers=desk).json()["entries"]
    assert ledger  # the claim is there; who is in the metadata, checked below
    container = api.app.state.container
    entry = container.ledger.for_patient("P-A")[-1]
    assert entry.metadata["confirmed_by"] == "Imran"


def test_the_approver_is_whoever_signed_in_not_whoever_the_body_says(api):
    """The treatment gate checks the role, so the role cannot be typed in."""
    seen = {}

    async def capture(**kwargs):
        seen.update(kwargs)
        raise LookupError("no options to approve")

    api.app.state.container.runner.approve_option = capture
    body = {"patient_id": "P-A", "option_index": 0,
            "approved_by_role": "doctor", "approved_by": "Dr Impostor"}

    nav = api.post("/api/disruptions/d1/approve", json=body, headers=sign_in(api, "seema"))
    desk = api.post("/api/disruptions/d1/approve", json=body, headers=sign_in(api, "imran"))

    assert nav.status_code == 404  # got past the gate, found nothing
    assert seen["approved_by_role"] is Role.NAVIGATOR
    assert seen["approved_by"] == "Seema"
    assert desk.status_code == 403, "a desk may not approve a re-plan at all"


# ---------------------------------------------------------------- families


def _register_two_families(api):
    nav = sign_in(api, "seema")
    api.post("/api/patients", json=PATIENT, headers=nav)
    api.post("/api/patients", headers=nav, json={
        **PATIENT, "id": "P-B", "name": "Banerjee family", "caregiver_phone": "+919811100000"})
    return nav


def test_a_family_signs_in_with_a_phone_and_a_code(api):
    _register_two_families(api)

    headers = caregiver(api, "+91 98000 11122")

    me = api.get("/api/auth/me", headers=headers).json()
    assert me["role"] == "caregiver"
    assert me["patient_ids"] == ["P-A"]


def verify(api, code):
    return api.post("/api/auth/otp/verify", json={"phone": "9800011122", "code": code})


def test_a_wrong_code_is_refused_and_five_wrong_codes_burn_it(api):
    _register_two_families(api)
    api.post("/api/auth/otp/request", json={"phone": "9800011122"})
    real = api.outbox.codes["9800011122"]
    wrong = "000000" if real != "000000" else "111111"

    for _ in range(5):
        assert verify(api, wrong).status_code == 401

    assert verify(api, real).status_code == 401


def test_asking_for_a_code_does_not_reveal_whether_a_number_is_on_record(api):
    _register_two_families(api)

    known = api.post("/api/auth/otp/request", json={"phone": "9800011122"})
    unknown = api.post("/api/auth/otp/request", json={"phone": "9000000000"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert "9000000000" not in api.outbox.codes


def test_a_family_sees_only_its_own(api):
    _register_two_families(api)
    mine = caregiver(api)

    assert [p["id"] for p in api.get("/api/patients", headers=mine).json()] == ["P-A"]
    assert api.get("/api/patients/P-A/home", headers=mine).status_code == 200
    assert api.get("/api/patients/P-A/steps", headers=mine).status_code == 200
    # Another family looks like one that does not exist.
    assert api.get("/api/patients/P-B/home", headers=mine).status_code == 404
    assert api.get("/api/patients/P-B/notifications", headers=mine).status_code == 404
    other = api.patch("/api/patients/P-B/language", json={"language": "en"}, headers=mine)
    assert other.status_code == 404


def test_a_family_cannot_use_a_staff_screen(api):
    _register_two_families(api)
    mine = caregiver(api)

    for path in ("/api/live", "/api/alerts", "/api/boards", "/api/ledger", "/api/desk/queue"):
        assert api.get(path, headers=mine).status_code == 403, path
    assert api.post("/api/patients", json=PATIENT, headers=mine).status_code == 403


def test_only_the_family_can_write_as_the_family(api):
    _register_two_families(api)
    body = {"patient_id": "P-A", "text": "when do we come?"}

    staff = api.post("/api/live/inject", json=body, headers=sign_in(api, "seema"))
    assert staff.status_code == 403
    mine = caregiver(api)
    other = api.post("/api/live/inject", json={**body, "patient_id": "P-B"}, headers=mine)
    assert other.status_code == 404


# ---------------------------------------------------------------- the event stream


def test_a_stream_ticket_works_once(api):
    ticket = api.post("/api/auth/stream-ticket", headers=sign_in(api, "seema")).json()["ticket"]
    identity = api.app.state.container.identity

    assert identity.redeem_stream_ticket(ticket) is not None
    assert identity.redeem_stream_ticket(ticket) is None


def test_the_stream_refuses_a_visitor_with_no_ticket(api):
    assert api.get("/api/stream").status_code == 401


async def _frames(container, principal, patients=("P-A", "P-B")):
    request = Request({"type": "http", "method": "GET", "path": "/api/stream",
                       "headers": [], "app": None})
    for pid in patients:
        container.bus.publish("plan.recomputed", "2026-01-01", patient_id=pid, summary=pid)
    container.bus.publish("clock.tick", "2026-01-01", summary="a day passed")
    ticket = container.identity.issue_stream_ticket(principal)
    response = await stream(request, container, ticket=ticket)
    seen = []
    while True:
        try:
            seen.append(await asyncio.wait_for(response.body_iterator.__anext__(), 0.3))
        except TimeoutError:
            return "".join(seen)


async def test_a_family_hears_only_events_about_itself(tmp_path):
    container = build_container(Settings(
        _env_file=None, world="real", auth="on", records_url=f"sqlite:///{tmp_path}/s.db"))
    from saathi.ports.identity import Principal

    family = Principal(id="c", name="A", role=Role.CAREGIVER, patient_ids=("P-A",))
    staff = Principal(id="s", name="S", role=Role.NAVIGATOR)

    family_view = await _frames(container, family)
    staff_view = await _frames(container, staff)

    assert "P-A" in family_view and "P-B" not in family_view
    assert "a day passed" not in family_view, "events about no family are not theirs either"
    assert "P-A" in staff_view and "P-B" in staff_view


# ---------------------------------------------------------------- settings


def test_production_refuses_to_start_without_a_real_secret_or_provider():
    with pytest.raises(ValueError, match="at least 32 characters"):
        Settings(_env_file=None, world="real", environment="production", identity_provider="oidc")
    with pytest.raises(ValueError, match="oidc"):
        Settings(_env_file=None, world="real", environment="production", auth_secret="x" * 40)
    with pytest.raises(ValueError, match="AUTH=off"):
        Settings(_env_file=None, environment="production")


def test_choosing_single_sign_on_fails_loudly_rather_than_falling_back(tmp_path):
    with pytest.raises(NotImplementedError, match="oidc"):
        build_container(Settings(
            _env_file=None, world="real", identity_provider="oidc",
            records_url=f"sqlite:///{tmp_path}/o.db"))


def test_a_password_account_must_be_staff_and_not_trivially_short(tmp_path):
    from saathi.adapters.records.sql import migrate

    migrate(f"sqlite:///{tmp_path}/u.db")
    identity = LocalIdentity(f"sqlite:///{tmp_path}/u.db", secret="x" * 40, phones=_NoPhones())
    with pytest.raises(ValueError, match="staff"):
        identity.add_user("fam", "Family", Role.CAREGIVER, PASSWORD)
    with pytest.raises(ValueError, match="8 characters"):
        identity.add_user("imran", "Imran", Role.DESK, "short")
