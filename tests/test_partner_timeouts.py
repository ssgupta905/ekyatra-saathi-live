"""An organisation that never answers: silence becomes UNKNOWN, not an endless "asked"."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from saathi.config import get_settings
from saathi.domain.directory import PartnerMode
from saathi.domain.enums import ReadinessKind, ReadinessStatus, Role
from saathi.main import create_app

PASSWORD = "correct horse battery"
TRANSPORT = ReadinessKind.TRANSPORT


@pytest.fixture
def net(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/timeouts.db")
    monkeypatch.setenv("SAATHI_SEED_DEMO", "true")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        container = client.app.state.container
        container.identity.add_user("neha", "Neha", Role.ADMIN, PASSWORD)
        token = client.post(
            "/api/auth/login", json={"username": "neha", "password": PASSWORD}
        ).json()["token"]
        client.headers["authorization"] = f"Bearer {token}"
        client.desk = container.runner.partners
        client.runner = container.runner
        client.world = container.world
        yield client
    get_settings.cache_clear()


def _ride(net, pid="SHOW-DIA-1"):
    return {i.kind: i for i in net.world.readiness_for(pid)}[TRANSPORT]


def _later(net, minutes):
    net.desk._now = lambda: datetime.now(UTC) + timedelta(minutes=minutes)
    return net.portal.call(net.runner.settle_partners)


def test_every_ask_carries_a_deadline_whoever_answers_it(net):
    assert _ride(net).answer_by is not None


def test_a_person_who_never_answers_leaves_the_family_uncertain_not_waiting_for_ever(net):
    ride = _ride(net)
    net.patch(f"/api/directory/{ride.partner_id}", json={"mode": PartnerMode.PEOPLE.value})

    _later(net, minutes=60)
    assert _ride(net).status is ReadinessStatus.PENDING, "an hour of silence is still just asked"

    _later(net, minutes=7 * 60)

    silent = _ride(net)
    assert silent.status is ReadinessStatus.UNKNOWN
    assert silent.answer_by is None and "no answer" in silent.detail
    assert net.get("/api/patients/SHOW-DIA-1/board").json()["decision"] == "uncertain"


def test_an_organisation_that_answered_in_time_is_never_expired(net):
    _later(net, minutes=10)
    assert _ride(net).status is ReadinessStatus.READY

    _later(net, minutes=24 * 60)

    assert _ride(net).status is ReadinessStatus.READY


def test_asking_again_gives_a_fresh_deadline(net):
    ride = _ride(net)
    net.patch(f"/api/directory/{ride.partner_id}", json={"mode": PartnerMode.PEOPLE.value})
    _later(net, minutes=7 * 60)
    assert _ride(net).status is ReadinessStatus.UNKNOWN

    net.desk._now = lambda: datetime.now(UTC)
    again = net.desk.ask("SHOW-DIA-1", TRANSPORT, ride.partner_id)

    assert again.status is ReadinessStatus.PENDING and again.answer_by is not None
