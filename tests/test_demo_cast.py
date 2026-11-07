"""The three scripted families, played through: smooth, a failed vendor, a second condition."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from saathi.config import get_settings
from saathi.domain.enums import Role
from saathi.main import create_app

PASSWORD = "correct horse battery"
EMAILS = ["one@example.com", "Two@Example.com", "three@example.com"]


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/cast.db")
    monkeypatch.setenv("SAATHI_SEED_DEMO", "true")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        container = client.app.state.container
        for name, role in (("neha", Role.ADMIN), ("imran", Role.DESK)):
            container.identity.add_user(name, name.title(), role, PASSWORD)

        def sign_in(who: str) -> None:
            token = client.post(
                "/api/auth/login", json={"username": who, "password": PASSWORD}
            ).json()["token"]
            client.headers["authorization"] = f"Bearer {token}"

        client.sign_in = sign_in
        client.sign_in("neha")
        client.runner = container.runner
        client.world = container.world
        yield client
    get_settings.cache_clear()


def _later(demo, minutes=10):
    demo.runner.partners._now = lambda: datetime.now(UTC) + timedelta(minutes=minutes)
    return demo.portal.call(demo.runner.settle_partners)


def _guide(demo, pid):
    return demo.get(f"/api/patients/{pid}/guide").json()


def _kinds(guide, state):
    return [s["kind"] for s in guide["stages"] if s["state"] == state]


def test_only_an_administrator_loads_the_cast_and_it_wants_real_addresses(demo):
    demo.sign_in("imran")
    assert demo.post("/api/demo/cast", json={"emails": EMAILS}).status_code == 403

    demo.sign_in("neha")
    assert demo.post("/api/demo/cast", json={"emails": ["nope"]}).status_code == 422
    assert demo.post("/api/demo/cast", json={"emails": []}).status_code == 422


def test_each_family_gets_the_address_it_was_given_and_nobody_else_has_one(demo):
    loaded = demo.post("/api/demo/cast", json={"emails": EMAILS}).json()["families"]

    assert [f["email"] for f in loaded] == [
        "one@example.com", "two@example.com", "three@example.com",
    ]
    holders = {p["id"]: p["caregiver_email"] for p in demo.get("/api/patients").json()
               if p["caregiver_email"]}
    assert holders == {"DEMO-1": "one@example.com", "DEMO-2": "two@example.com",
                       "DEMO-3": "three@example.com"}


def test_the_smooth_journey_waits_for_the_report_then_every_party_answers_and_it_goes(demo):
    demo.post("/api/demo/cast", json={"emails": EMAILS})
    first = _guide(demo, "DEMO-1")
    assert first["now_stage_id"] == "reports" and _kinds(first, "waiting") == ["reports"]
    assert demo.world.readiness_for("DEMO-1") == (), "nobody is asked before the report lands"

    demo.world.apply_release("DEMO-1-pathology_report")
    demo.portal.call(demo.runner.plan_patient, "DEMO-1")
    assert {i.kind.value for i in demo.world.readiness_for("DEMO-1")} >= {
        "insurance", "medicine", "transport",
    }
    _later(demo)

    done = _guide(demo, "DEMO-1")
    assert done["decision"] == "go"
    visit = next(s for s in done["stages"] if s["kind"] == "visit")
    assert visit["on"] and visit["first_stop"]
    thread = demo.get("/api/patients/DEMO-1/notifications").json()["thread"]
    assert any(m["kind"] == "guide" for m in thread), "the family was told along the way"


def test_the_vendor_failure_shows_a_problem_then_staff_book_another_and_it_recovers(demo):
    demo.post("/api/demo/cast", json={"emails": EMAILS})
    asked = {i.kind.value: i for i in demo.world.readiness_for("DEMO-2")}
    assert asked["transport"].partner_id == "cab-uber", "staff chose Uber for this family"

    _later(demo)

    problem = _guide(demo, "DEMO-2")
    assert _kinds(problem, "problem") == ["ride"]
    assert problem["decision"] == "replan"
    assert all(s["on"] is None for s in problem["stages"]), "no date while the ride is a problem"

    booked = demo.post("/api/patients/DEMO-2/readiness/DEMO-2-transport/rebook")
    assert booked.json()["item"]["party"] == "Ola"
    _later(demo, minutes=20)

    assert _guide(demo, "DEMO-2")["decision"] == "go"


def test_the_second_condition_runs_on_the_same_engine_with_its_own_chain(demo):
    demo.post("/api/demo/cast", json={"emails": EMAILS})
    guide = _guide(demo, "DEMO-3")

    kinds = [s["kind"] for s in guide["stages"]]
    assert "next_session" in kinds and "ride" in kinds
    assert [s["kind"] for s in guide["stages"]][-1] == "next_session"
    _later(demo)
    assert _guide(demo, "DEMO-3")["decision"] == "go"
    stages = _guide(demo, "DEMO-3")["stages"]
    assert next(s for s in stages if s["kind"] == "next_session")["on"] is None


def test_loading_again_puts_every_family_back_at_the_start_of_its_story(demo):
    demo.post("/api/demo/cast", json={"emails": EMAILS})
    demo.world.apply_release("DEMO-1-pathology_report")
    demo.portal.call(demo.runner.plan_patient, "DEMO-1")
    _later(demo)
    assert _guide(demo, "DEMO-1")["decision"] == "go"

    again = demo.post("/api/demo/cast", json={"emails": EMAILS})

    assert again.status_code == 200
    reset = _guide(demo, "DEMO-1")
    assert reset["now_stage_id"] == "reports" and reset["decision"] != "go"
    assert demo.world.readiness_for("DEMO-1") == ()


def test_an_address_given_to_the_cast_is_taken_from_any_other_family(demo):
    demo.world.update_patient("P0000", caregiver_email="one@example.com")

    demo.post("/api/demo/cast", json={"emails": EMAILS})

    holders = [p["id"] for p in demo.get("/api/patients").json()
               if p["caregiver_email"] == "one@example.com"]
    assert holders == ["DEMO-1"]


def test_loading_again_also_starts_each_family_s_conversation_again(demo):
    demo.post("/api/demo/cast", json={"emails": EMAILS})
    demo.world.apply_release("DEMO-1-pathology_report")
    demo.portal.call(demo.runner.plan_patient, "DEMO-1")
    _later(demo)
    told = [r for r in demo.runner.outbound if r["patient_id"] == "DEMO-1"]
    assert told, "the family was told something along the way"

    demo.post("/api/demo/cast", json={"emails": EMAILS})

    assert not [r for r in demo.runner.outbound if r["patient_id"] == "DEMO-1"]
    stored = demo.runner.world.store.load().family_messages
    assert not [m for m in stored if m["patient_id"] == "DEMO-1"]
