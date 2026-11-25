"""What a family's ride and stay apps are opened on: the hospital's door, a date only on a GO."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from saathi.config import get_settings
from saathi.domain.enums import Role
from saathi.main import create_app

PASSWORD = "correct horse battery"
EMAILS = ["anita@example.com", "ravi@example.com", "meena@example.com"]


class Outbox:
    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    def send(self, email: str, code: str) -> None:
        self.codes[email] = code


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/trip.db")
    monkeypatch.setenv("SAATHI_SEED_DEMO", "true")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        container = client.app.state.container
        outbox = Outbox()
        container.identity._email_sender = outbox
        container.identity.add_user("neha", "Neha", Role.ADMIN, PASSWORD)
        token = client.post(
            "/api/auth/login", json={"username": "neha", "password": PASSWORD}
        ).json()["token"]
        client.staff = {"authorization": f"Bearer {token}"}
        client.post("/api/demo/cast", json={"emails": EMAILS}, headers=client.staff)

        def family(email):
            client.post("/api/auth/otp/request", json={"email": email})
            signed = client.post(
                "/api/auth/otp/verify", json={"email": email, "code": outbox.codes[email]}
            ).json()["token"]
            return {"authorization": f"Bearer {signed}"}

        client.family = family
        client.container = container
        yield client
    get_settings.cache_clear()


def _trip(app, pid, email):
    return app.get(f"/api/patients/{pid}/guide", headers=app.family(email)).json()["trip"]


def test_the_trip_names_the_hospital_s_door_and_no_pickup(app):
    trip = _trip(app, "DEMO-1", "anita@example.com")

    where = trip["destination"]
    assert where["name"] == "Tata Memorial Hospital, Mumbai"
    assert 18.9 < where["latitude"] < 19.1 and 72.7 < where["longitude"] < 73.0
    assert "Parel" in where["address"]
    # Where a family is staying never passes through Saathi: the app uses the phone's location.
    assert not any(k in trip for k in ("pickup", "origin", "home", "district"))


def test_the_day_is_given_only_when_the_plan_is_a_go(app):
    from datetime import UTC, datetime, timedelta

    waiting = _trip(app, "DEMO-1", "anita@example.com")  # the report is still with the lab
    assert waiting["arrive_on"] is None, "no date is promised before the plan says go"

    app.container.world.apply_release("DEMO-1-pathology_report")
    runner = app.container.runner
    app.portal.call(runner.plan_patient, "DEMO-1")
    runner.partners._now = lambda: datetime.now(UTC) + timedelta(minutes=10)
    app.portal.call(runner.settle_partners)

    anita = app.family("anita@example.com")
    guide = app.get("/api/patients/DEMO-1/guide", headers=anita).json()
    assert guide["decision"] == "go"
    visit = next(s for s in guide["stages"] if s["kind"] == "visit")
    assert guide["trip"]["arrive_on"] == visit["on"] and visit["on"] is not None


def test_a_hospital_without_an_entrance_gives_no_destination_not_a_guess(app):
    registry = app.container.registry
    hospital = next(h for h in registry.hospitals() if h.id == "TMH-MUM")
    registry.save_hospital(hospital.model_copy(update={"latitude": None, "longitude": None}))

    assert _trip(app, "DEMO-1", "anita@example.com")["destination"] is None


def test_the_entrance_top_up_never_overwrites_one_an_admin_set(app):
    from saathi.bootstrap.seed import top_up_entrances

    registry = app.container.registry
    hospital = next(h for h in registry.hospitals() if h.id == "TMH-MUM")
    registry.save_hospital(hospital.model_copy(update={"latitude": 1.5, "longitude": 2.5}))

    assert top_up_entrances(registry) == 0
    kept = next(h for h in registry.hospitals() if h.id == "TMH-MUM")
    assert (kept.latitude, kept.longitude) == (1.5, 2.5)


def test_an_admin_can_set_a_hospital_s_entrance(app):
    done = app.patch(
        "/api/registry/hospitals/HBCH-MZP",
        json={"latitude": 26.12, "longitude": 85.39, "address": "Main gate, Muzaffarpur"},
        headers=app.staff,
    )

    assert done.status_code == 200
    listed = app.get("/api/registry/hospitals", headers=app.staff).json()
    mine = next(h for h in listed if h["id"] == "HBCH-MZP")
    assert mine["latitude"] == 26.12 and mine["address"] == "Main gate, Muzaffarpur"
