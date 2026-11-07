"""Asking the family what they can manage, and what happens to the answer.

The point of the conversation is that the system stops guessing. These pin the
round trip — the question is built from real organisations, the answer changes
nothing until a person agrees, and the two different kinds of answer go to two
different places.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from saathi.config import get_settings
from saathi.domain.budget import TOPIC_CHOICE_KEY, BudgetTopic
from saathi.domain.enums import ReadinessStatus, Role
from saathi.main import create_app

PASSWORD = "correct horse battery"


@pytest.fixture
def net(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/budget.db")
    monkeypatch.setenv("SAATHI_SEED_DEMO", "true")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        client.container = client.app.state.container
        client.container.identity.add_user("neha", "Neha", Role.NAVIGATOR, PASSWORD)
        yield client
    get_settings.cache_clear()


def _as(client, username: str) -> dict:
    token = client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    ).json()["token"]
    return {"authorization": f"Bearer {token}"}


def _family_being_asked(net) -> str:
    """A family the desk has already asked somebody about."""
    for patient in net.container.world.patients():
        items = net.container.world.readiness_for(patient.id)
        if any(i.partner_id and i.status is ReadinessStatus.PENDING for i in items):
            return patient.id
    raise AssertionError("nobody is waiting on an organisation")


def _set_background(net, patient_id: str, **answers) -> None:
    net.container.onboarding.save_section(patient_id, "background", answers, "neha")


# ---------------------------------------------------------- the question ----


def test_every_option_offered_is_a_real_organisation_that_serves_this_family(net):
    """Nothing is composed for the screen.

    A family tapping "railway patient quota desk" is choosing a desk that is in
    the directory and that will actually be asked.
    """
    patient_id = _family_being_asked(net)
    staff = _as(net, "neha")

    body = net.get(f"/api/patients/{patient_id}/budget", headers=staff).json()
    assert body["asks"], "a family waiting on a ride should be asked about it"

    known = {o.id: o for o in net.container.registry.organisations()}
    for ask in body["asks"]:
        assert ask["options"]
        for option in ask["options"]:
            org = known.get(option["organisation_id"])
            assert org is not None and org.active
            assert option["name"] == org.name
            # Its own words from the directory, not a label written for a screen.
            assert list(option["what"]) == list(org.services)


def test_no_option_carries_a_price(net):
    """This project does not report a fare it was not given, here either."""
    patient_id = _family_being_asked(net)
    body = net.get(f"/api/patients/{patient_id}/budget", headers=_as(net, "neha")).json()
    text = str(body)
    for money in ("rupee", "₹", "price", "amount", "total", "per_km"):
        assert money not in text.lower()


def test_the_choice_is_between_different_kinds_of_thing_not_three_cabs(net):
    """One organisation per tier.

    Five near-identical options to somebody on a 2G phone in a second language
    is not more choice; it is a way of not being answered.
    """
    patient_id = _family_being_asked(net)
    body = net.get(f"/api/patients/{patient_id}/budget", headers=_as(net, "neha")).json()
    for ask in body["asks"]:
        tiers = [o["cost_tier"] for o in ask["options"]]
        assert len(tiers) == len(set(tiers)), ask["topic"]
        assert len(tiers) <= 3


def test_a_family_on_the_lowest_band_is_offered_the_cheap_thing_first(net):
    patient_id = _family_being_asked(net)
    _set_background(net, patient_id, ration_card="aay")

    body = net.get(f"/api/patients/{patient_id}/budget", headers=_as(net, "neha")).json()
    travel = next((a for a in body["asks"] if a["topic"] == "travel"), None)
    if travel is None:
        pytest.skip("this family's journey has no travel need")
    assert travel["options"][0]["cost_tier"] == "subsidised"
    # Marked, never pre-selected: a default that was merely not changed is not
    # an answer to "what can you manage".
    assert travel["options"][0]["suggested"] is True


def test_the_family_can_always_say_they_cannot_manage_any_of_it(net):
    patient_id = _family_being_asked(net)
    body = net.get(f"/api/patients/{patient_id}/budget", headers=_as(net, "neha")).json()
    assert all(ask["can_say_cannot_manage"] for ask in body["asks"])


# ------------------------------------------------------------ the answer ----


def _first_topic(net, patient_id, staff):
    body = net.get(f"/api/patients/{patient_id}/budget", headers=staff).json()
    if not body["asks"]:
        pytest.skip("nothing to ask this family about")
    return body["asks"][0]


def test_an_answer_changes_nothing_until_a_person_agrees(net):
    patient_id = _family_being_asked(net)
    staff = _as(net, "neha")
    ask = _first_topic(net, patient_id, staff)
    chosen = ask["options"][-1]["organisation_id"]

    before = net.container.onboarding.section(patient_id, "partners")
    reply = net.post(
        f"/api/patients/{patient_id}/budget/{ask['topic']}",
        json={"organisation_id": chosen},
        headers=staff,
    )
    assert reply.status_code == 200
    assert reply.json()["awaiting_confirmation"] is True
    assert net.container.onboarding.section(patient_id, "partners") == before

    waiting = net.get("/api/budget/waiting", headers=staff).json()
    assert any(r["patient_id"] == patient_id and r["topic"] == ask["topic"] for r in waiting)


def test_once_confirmed_the_family_s_choice_is_the_one_that_gets_asked(net):
    patient_id = _family_being_asked(net)
    staff = _as(net, "neha")
    ask = _first_topic(net, patient_id, staff)
    chosen = ask["options"][-1]["organisation_id"]
    kind = ask["need"]

    net.post(
        f"/api/patients/{patient_id}/budget/{ask['topic']}",
        json={"organisation_id": chosen},
        headers=staff,
    )
    done = net.post(
        f"/api/patients/{patient_id}/budget/{ask['topic']}/confirm", headers=staff
    )
    assert done.status_code == 200

    saved = net.container.onboarding.section(patient_id, "partners")
    assert saved is not None and saved[0].get(TOPIC_CHOICE_KEY[BudgetTopic(ask["topic"])]) == chosen

    # And the row on the network board now names who they chose.
    item = next(
        (i for i in net.container.world.readiness_for(patient_id) if i.kind.value == kind), None
    )
    assert item is not None and item.partner_id == chosen


def test_cannot_manage_raises_a_person_and_does_not_rebook_anything(net):
    """The most important answer, and the one that is not a booking.

    A family with no fare needs a person and a scheme. Quietly moving them to a
    cheaper cab would look like help and would not be.
    """
    patient_id = _family_being_asked(net)
    staff = _as(net, "neha")
    ask = _first_topic(net, patient_id, staff)
    before = net.container.onboarding.section(patient_id, "partners")

    net.post(
        f"/api/patients/{patient_id}/budget/{ask['topic']}",
        json={"cannot_manage": True, "said": "there is no money for the fare this month"},
        headers=staff,
    )
    net.post(f"/api/patients/{patient_id}/budget/{ask['topic']}/confirm", headers=staff)

    assert net.container.onboarding.section(patient_id, "partners") == before
    raised = [a for a in net.container.runner.alerts if a.patient_id == patient_id]
    assert any(a.kind.value == "needs_help" for a in raised)
    assert any("fare" in a.detail for a in raised)


def test_an_empty_answer_is_refused_rather_than_recorded_as_nothing(net):
    patient_id = _family_being_asked(net)
    staff = _as(net, "neha")
    ask = _first_topic(net, patient_id, staff)
    reply = net.post(
        f"/api/patients/{patient_id}/budget/{ask['topic']}", json={}, headers=staff
    )
    assert reply.status_code == 422


def test_confirming_something_nobody_said_is_a_404_not_a_silent_success(net):
    patient_id = _family_being_asked(net)
    reply = net.post(
        f"/api/patients/{patient_id}/budget/stay/confirm", headers=_as(net, "neha")
    )
    assert reply.status_code == 404


# ------------------------------------------------- with login switched off ----


@pytest.fixture
def open_door(tmp_path, monkeypatch):
    """The demo's own configuration: a real world with no sign-in.

    Worth its own fixture. Every other test here signs in, so none of them
    exercises the path where `PrincipalDep` is None — which is the path the
    recorded demo takes, and the one where confirming an answer first
    returned a 500.
    """
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_AUTH", "off")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/open.db")
    monkeypatch.setenv("SAATHI_SEED_DEMO", "true")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        client.container = client.app.state.container
        yield client
    get_settings.cache_clear()


def test_confirming_works_with_nobody_signed_in(open_door):
    patient_id = _family_being_asked(open_door)
    body = open_door.get(f"/api/patients/{patient_id}/budget").json()
    if not body["asks"]:
        pytest.skip("nothing to ask this family about")
    ask = body["asks"][0]

    open_door.post(
        f"/api/patients/{patient_id}/budget/{ask['topic']}",
        json={"organisation_id": ask["options"][-1]["organisation_id"]},
    )
    done = open_door.post(f"/api/patients/{patient_id}/budget/{ask['topic']}/confirm")

    assert done.status_code == 200, done.text
    # Recorded against somebody, even when nobody is signed in: an audit row
    # saying None is worse than one saying "staff".
    assert done.json()["answer"]["confirmed_by"]
