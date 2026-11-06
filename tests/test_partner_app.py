"""What a vendor can see, and what it must not.

A partner signs in with a password like staff do, and that is where the
resemblance ends. The tests that matter here are the negative ones: a cab firm
must not be able to read a family's care, a second organisation's jobs, or a
phone number the family has not agreed to share. Those are the failures that do
not announce themselves.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from saathi.config import get_settings
from saathi.domain.directory import PartnerMode
from saathi.domain.enums import ReadinessStatus, Role
from saathi.main import create_app

PASSWORD = "correct horse battery"
OLA = "cab-ola"
UBER = "cab-uber"


@pytest.fixture
def net(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/partner.db")
    monkeypatch.setenv("SAATHI_SEED_DEMO", "true")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        container = client.app.state.container
        container.identity.add_user("neha", "Neha", Role.ADMIN, PASSWORD)
        container.identity.add_user(
            "ola", "Ola", Role.PARTNER, PASSWORD, organisation_id=OLA
        )
        container.identity.add_user(
            "uber", "Uber", Role.PARTNER, PASSWORD, organisation_id=UBER
        )
        client.container = container
        yield client
    get_settings.cache_clear()


def _as(client, username: str) -> dict:
    token = client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    ).json()["token"]
    return {"authorization": f"Bearer {token}"}


def _give_ola_a_job(net) -> tuple[str, str]:
    """Ask Ola for a ride, as a navigator would when Uber has failed."""
    world = net.container.world
    desk = net.container.runner.partners
    # A vendor with people behind it is never auto-answered; that is the point.
    registry = net.container.registry
    ola = next(o for o in registry.organisations() if o.id == OLA)
    registry.save_organisation(ola.model_copy(update={"mode": PartnerMode.PEOPLE}))

    # A family with a name: the synthetic cohort has none, and a job for one
    # of those cannot show what a vendor is and is not told about a person.
    for patient in world.patients():
        if not patient.name:
            continue
        for item in world.readiness_for(patient.id):
            if item.partner_id and item.status is ReadinessStatus.PENDING:
                moved = desk.ask(patient.id, item.kind, OLA)
                return patient.id, moved.id
    raise AssertionError("no named family is waiting on anybody")


# ---------------------------------------------------------------- who sees what


def test_a_partner_sees_only_its_own_organisations_jobs(net):
    patient_id, item_id = _give_ola_a_job(net)

    mine = net.get("/api/partner/jobs", headers=_as(net, "ola")).json()
    theirs = net.get("/api/partner/jobs", headers=_as(net, "uber")).json()

    assert item_id in [j["item_id"] for j in mine["jobs"]]
    assert item_id not in [j["item_id"] for j in theirs["jobs"]]
    # Nothing in Ola's queue belongs to anybody else, however the seed grew.
    assert mine["organisation"]["id"] == OLA
    assert not set(j["item_id"] for j in mine["jobs"]) & set(
        j["item_id"] for j in theirs["jobs"]
    )


def test_a_partner_learns_nothing_about_any_family(net):
    """A cab firm has no business here, by refusal or by empty answer.

    Both count. `/api/patients` answers 200 with an empty list, because a
    partner may see nobody and the filter is the same one a caregiver gets;
    the rest refuse outright. What must never happen is a body with a family
    in it, so that is what this asserts rather than a particular status code.
    """
    patient_id, _ = _give_ola_a_job(net)
    headers = _as(net, "ola")
    patient = net.container.world.patient(patient_id)

    for path in (
        f"/api/patients/{patient_id}/guide",
        f"/api/patients/{patient_id}/steps",
        "/api/patients",
        "/api/boards",
        "/api/network",
        "/api/ledger",
    ):
        answer = net.get(path, headers=headers)
        assert answer.status_code in {200, 401, 403, 404}, path
        body = answer.text
        assert patient_id not in body, f"{path} named a family to a vendor"
        if patient.name:
            assert patient.name not in body, f"{path} named a family to a vendor"


def test_a_job_carries_no_clinical_word_and_no_surname(net):
    patient_id, _ = _give_ola_a_job(net)

    job = net.get("/api/partner/jobs", headers=_as(net, "ola")).json()["jobs"][0]

    patient = net.container.world.patient(patient_id)
    assert patient.name, "this test needs a named family to mean anything"
    assert job["family"]["first_name"] == patient.name.split(" ")[0]
    if " " in patient.name:
        assert patient.name not in str(job), "the whole name should not reach a vendor"
    body = str(job).lower()
    for word in ("cancer", "dialysis", "biopsy", "report", "diagnosis", "chemo"):
        assert word not in body, f"a vendor was told about {word}"


def test_a_phone_number_needs_the_family_to_have_agreed(net):
    """No grant, no contact — and the job says so rather than going quiet."""
    _give_ola_a_job(net)

    job = net.get("/api/partner/jobs", headers=_as(net, "ola")).json()["jobs"][0]

    assert job["family"]["contact"] is None
    assert job["family"]["contact_withheld"] is True


# ---------------------------------------------------------------- answering


def test_ready_moves_the_family_on(net):
    patient_id, item_id = _give_ola_a_job(net)

    answered = net.post(
        f"/api/partner/jobs/{item_id}",
        json={"answer": "ready"},
        headers=_as(net, "ola"),
    )

    assert answered.status_code == 200, answered.text
    item = next(i for i in net.container.world.readiness_for(patient_id) if i.id == item_id)
    assert item.status is ReadinessStatus.READY
    assert "Ola" in item.detail


def test_cannot_do_needs_a_reason_because_someone_must_book_another(net):
    _, item_id = _give_ola_a_job(net)
    headers = _as(net, "ola")

    silent = net.post(f"/api/partner/jobs/{item_id}", json={"answer": "cannot"}, headers=headers)
    spoken = net.post(
        f"/api/partner/jobs/{item_id}",
        json={"answer": "cannot", "reason": "no car in that district tonight"},
        headers=headers,
    )

    assert silent.status_code == 422
    assert spoken.status_code == 200
    assert "no car in that district" in spoken.json()["detail"]


def test_a_partner_cannot_answer_another_organisations_job(net):
    _, item_id = _give_ola_a_job(net)

    refused = net.post(
        f"/api/partner/jobs/{item_id}", json={"answer": "ready"}, headers=_as(net, "uber")
    )

    # 404, not 403: the shape of the refusal must not reveal that it exists.
    assert refused.status_code == 404


def test_an_account_bound_to_nobody_sees_nothing(net):
    with pytest.raises(ValueError, match="which organisation"):
        net.container.identity.add_user("ghost", "Ghost", Role.PARTNER, PASSWORD)


def test_staff_cannot_use_the_partner_queue(net):
    """It is not a second way into the same data for people who already have one."""
    assert net.get("/api/partner/jobs", headers=_as(net, "neha")).status_code == 403
