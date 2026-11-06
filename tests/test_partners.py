"""The network answering a journey: who is needed, who is asked, who answers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from saathi.bootstrap.demo_directory import DEMO_DIRECTORY
from saathi.config import get_settings
from saathi.domain.directory import Organisation, OrgType, PartnerMode
from saathi.domain.enums import ReadinessKind, ReadinessStatus, Role, StepKind
from saathi.domain.models import ReadinessItem
from saathi.domain.pathway import DIALYSIS, ONCOLOGY
from saathi.main import create_app
from saathi.orchestrator import choose_organisation, missing_needs, needs_for

PASSWORD = "correct horse battery"
TRANSPORT = ReadinessKind.TRANSPORT


# ---------------------------------------------------------------- the pure rules


def test_a_journey_needs_what_its_pathway_says_and_a_stay_only_when_far():
    far = needs_for(ONCOLOGY, StepKind.REVIEW_CONSULT, round_trip_hours=30, stay_threshold_hours=12)
    near = needs_for(ONCOLOGY, StepKind.REVIEW_CONSULT, round_trip_hours=3, stay_threshold_hours=12)
    unknown = needs_for(
        ONCOLOGY, StepKind.REVIEW_CONSULT, round_trip_hours=None, stay_threshold_hours=12
    )

    assert ReadinessKind.STAY in far and ReadinessKind.STAY not in near
    assert ReadinessKind.STAY in unknown, "when the journey is unknown, leave nobody without a bed"
    assert set(near) == {
        ReadinessKind.SLOT, ReadinessKind.DOCTOR,
        ReadinessKind.INSURANCE, ReadinessKind.MEDICINE, TRANSPORT,
    }


def test_another_condition_needs_other_parties():
    needs = needs_for(
        DIALYSIS, StepKind.DIALYSIS_SESSION, round_trip_hours=2, stay_threshold_hours=12
    )

    assert needs == (ReadinessKind.SLOT, TRANSPORT)


def test_a_target_the_pathway_has_no_needs_for_asks_nobody():
    assert needs_for(ONCOLOGY, StepKind.BLOODS, round_trip_hours=30, stay_threshold_hours=12) == ()


def test_only_the_needs_nobody_has_been_asked_about_are_missing():
    asked = ReadinessItem(
        id="P-transport", patient_id="P", kind=TRANSPORT, party="Uber",
        status=ReadinessStatus.PENDING,
    )

    left = missing_needs((TRANSPORT, ReadinessKind.STAY), (asked,))

    assert left == (ReadinessKind.STAY,)


def _org(id, type_, **extra):
    return Organisation(id=id, name=extra.pop("name", id), type=type_, **extra)


def test_a_family_s_own_choice_wins_over_the_best_fit():
    orgs = [_org("a", OrgType.CAB, districts=("Patna",)), _org("b", OrgType.CAB)]

    chosen = choose_organisation(
        TRANSPORT, district="Patna", hospital_id="H", organisations=orgs, preferred_id="b"
    )

    assert chosen.id == "b"


def test_otherwise_the_first_that_serves_the_place_and_hospital_by_name():
    orgs = [
        _org("z", OrgType.CAB, name="Zed Cabs", districts=("Patna",)),
        _org("m", OrgType.CAB, name="Meru", districts=("Mumbai",)),
        _org("a", OrgType.CAB, name="Alpha Cabs", districts=("Patna",), hospital_ids=("OTHER",)),
        _org("o", OrgType.CAB, name="Ola", districts=("Patna",), hospital_ids=("H",)),
        _org("x", OrgType.CAB, name="Off", districts=("Patna",), active=False),
    ]

    chosen = choose_organisation(TRANSPORT, district="patna", hospital_id="H", organisations=orgs)

    # Alpha does not work with this hospital, Off is inactive, Meru is elsewhere.
    assert chosen.id == "o"


def test_a_cab_is_preferred_to_a_rail_desk_for_a_ride():
    orgs = [
        _org("r", OrgType.TRAVEL, name="Railway desk"),
        _org("c", OrgType.CAB, name="Zed Cabs"),
    ]

    chosen = choose_organisation(TRANSPORT, district="Gaya", hospital_id="H", organisations=orgs)

    assert chosen.id == "c"


def test_nobody_in_the_directory_means_nobody_is_asked():
    assert (
        choose_organisation(TRANSPORT, district="Gaya", hospital_id="H", organisations=[]) is None
    )


def test_the_demo_directory_can_serve_every_need_at_the_demo_hospital():
    for kind in (
        TRANSPORT, ReadinessKind.STAY, ReadinessKind.MEDICINE, ReadinessKind.INSURANCE,
        ReadinessKind.SLOT, ReadinessKind.DOCTOR,
    ):
        place = "Mumbai" if kind is not TRANSPORT else "Patna"
        assert choose_organisation(
            kind, district=place, hospital_id="TMH-MUM", organisations=DEMO_DIRECTORY
        ), kind


# ---------------------------------------------------------------- the desk, end to end


@pytest.fixture
def net(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/net.db")
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


def _items(net, pid):
    return {i.kind: i for i in net.world.readiness_for(pid)}


def _let_time_pass(net, minutes=10):
    net.desk._now = lambda: datetime.now(UTC) + timedelta(minutes=minutes)
    return net.portal.call(net.runner.settle_partners)


def test_a_family_whose_care_steps_are_ready_has_its_parties_asked_and_then_hears_back(net):
    asked = _items(net, "SHOW-DIA-1")

    assert asked[TRANSPORT].status is ReadinessStatus.PENDING
    assert asked[TRANSPORT].partner_id and asked[TRANSPORT].due_at is not None
    assert net.get("/api/patients/SHOW-DIA-1/board").json()["decision"] == "wait"

    answered = _let_time_pass(net)

    assert answered >= 1
    assert all(i.status is ReadinessStatus.READY for i in _items(net, "SHOW-DIA-1").values())
    assert net.get("/api/patients/SHOW-DIA-1/board").json()["decision"] == "go"


def test_a_family_whose_care_steps_are_not_ready_has_nobody_asked(net):
    assert _items(net, "SHOW-MRI-1") == {}, "the scan is still to come"


def test_each_need_is_asked_once_not_on_every_plan(net):
    before = {k: i.due_at for k, i in _items(net, "SHOW-DIA-1").items()}

    net.portal.call(net.runner.plan_patient, "SHOW-DIA-1")
    net.portal.call(net.runner.plan_patient, "SHOW-DIA-1")

    assert {k: i.due_at for k, i in _items(net, "SHOW-DIA-1").items()} == before


def test_an_organisation_that_cannot_makes_the_journey_a_replan_until_staff_book_another(net):
    asked = _items(net, "SHOW-DIA-1")[TRANSPORT]
    # Whoever the desk asked will say it cannot, and has another cab to turn to.
    net.patch(
        f"/api/directory/{asked.partner_id}",
        json={"answer": "cannot", "alternate_id": "cab-ola"},
    )
    net.world.set_readiness_item(asked.model_copy(update={"alternative_available": True}))

    _let_time_pass(net)

    blocked = _items(net, "SHOW-DIA-1")[TRANSPORT]
    assert blocked.status is ReadinessStatus.BLOCKED and blocked.alternative_available is True
    assert net.get("/api/patients/SHOW-DIA-1/board").json()["decision"] == "replan"

    booked = net.post(f"/api/patients/SHOW-DIA-1/readiness/{blocked.id}/rebook")

    assert booked.status_code == 200
    assert booked.json()["item"]["party"] == "Ola"
    assert booked.json()["item"]["status"] == "pending"
    assert booked.json()["decision"] == "wait", "waiting on the new cab, no longer a re-plan"


def test_booking_another_with_no_alternative_is_refused(net):
    item = _items(net, "SHOW-DIA-1")[TRANSPORT]
    net.patch(f"/api/directory/{item.partner_id}", json={"alternate_id": None})

    assert net.post(f"/api/patients/SHOW-DIA-1/readiness/{item.id}/rebook").status_code == 409


def test_an_organisation_that_waits_for_a_person_is_never_answered_by_the_desk(net):
    item = _items(net, "SHOW-DIA-1")[TRANSPORT]
    net.patch(f"/api/directory/{item.partner_id}", json={"mode": PartnerMode.PEOPLE.value})

    assert net.desk.settle(item) is None


def test_staff_can_ask_a_particular_organisation_instead(net):
    response = net.post(
        "/api/patients/SHOW-DIA-1/readiness/request",
        json={"kind": "transport", "organisation_id": "cab-uber"},
    )

    assert response.status_code == 201
    assert response.json()["item"]["party"] == "Uber"
    unknown = net.post(
        "/api/patients/SHOW-DIA-1/readiness/request",
        json={"kind": "transport", "organisation_id": "nobody"},
    )
    assert unknown.status_code == 422


def test_a_choice_saved_for_a_family_is_the_one_asked(net):
    net.put("/api/patients/SHOW-DIA-1/profile/partners", json={"transport": "cab-uber"})

    assert net.desk._preferred("SHOW-DIA-1", TRANSPORT) == "cab-uber"
    assert net.desk._preferred("SHOW-DIA-1", ReadinessKind.STAY) is None


# ---------------------------------------------------------------- what the apps read


def test_a_family_s_guide_shows_the_failed_party_as_a_problem_with_no_date(net):
    guide = net.get("/api/patients/SHOW-REPLAN-1/guide").json()

    ride = next(s for s in guide["stages"] if s["kind"] == "ride")
    assert ride["state"] == "problem" and ride["party"] == "Ola"
    assert ride["action"] == "wait_for_team"
    assert guide["decision"] == "replan"
    assert all(s["on"] is None for s in guide["stages"])
    assert guide["now_stage_id"] == "ride"


def test_the_family_s_home_carries_the_guide_beside_everything_it_already_had(net):
    home = net.get("/api/patients/SHOW-GO-1/home").json()

    assert {"decision", "steps", "waiting_for", "what_to_bring", "guide"} <= home.keys()
    visit = next(s for s in home["guide"]["stages"] if s["kind"] == "visit")
    assert visit["on"] == home["travel_on"], "the guide and the verdict can never disagree"


def test_the_network_board_puts_stuck_journeys_first_and_counts_what_each_party_holds(net):
    board = net.get("/api/network").json()

    assert board["families"][0]["patient_id"] == "SHOW-REPLAN-1" and board["families"][0]["stuck"]
    ola = next(p for p in board["parties"] if p["party"] == "Ola")
    assert ola["problem"] == 1
    assert {"patient_id", "name", "stages", "done", "total"} <= board["families"][0].keys()


def test_an_unknown_family_has_no_guide(net):
    assert net.get("/api/patients/NOBODY/guide").status_code == 404


def test_a_family_is_told_in_the_thread_when_their_journey_moves(net):
    _let_time_pass(net)

    thread = net.get("/api/patients/SHOW-DIA-1/notifications").json()["thread"]

    updates = [m for m in thread if m["kind"] == "guide"]
    assert updates, "the family heard that their journey moved"
    assert updates[-1]["rendered_by"] == "template"
    assert updates[-1]["language"] == "hi"



# ---------------------------------------------------------------- the hospital as a party


def test_the_hospital_is_asked_for_a_slot_and_a_doctor_like_any_other_party(net):
    asked = _items(net, "SHOW-DIA-1")
    assert asked[ReadinessKind.SLOT].party == "Tata Memorial Hospital, Mumbai"
    assert asked[ReadinessKind.SLOT].partner_id == "hosp-tmh-mum"

    onco = _items(net, "DEMO-1") or {}
    assert onco == {}, "the lab report is still to come, so nobody is asked yet"


def test_a_doctor_who_is_not_available_puts_the_journey_in_a_replan(net):
    net.patch(
        "/api/directory/hosp-tmh-mum",
        json={"answer": "cannot", "alternate_id": "hosp-hbch-mzp"},
    )
    net.post("/api/demo/cast", json={"emails": ["a@example.com", "b@example.com"]})

    _let_time_pass(net)

    doctor = _items(net, "DEMO-2")[ReadinessKind.DOCTOR]
    assert doctor.status is ReadinessStatus.BLOCKED and doctor.party.startswith("Tata Memorial")
    guide = net.get("/api/patients/DEMO-2/guide").json()
    assert next(s for s in guide["stages"] if s["kind"] == "doctor")["state"] == "problem"


def test_the_hospital_stages_come_before_the_family_is_asked_to_travel(net):
    guide = net.get("/api/patients/SHOW-GO-1/guide").json()

    order = [s["kind"] for s in guide["stages"]]
    assert order.index("appointment") < order.index("doctor") < order.index("ride")
    assert order.index("ride") < order.index("documents") < order.index("visit")


def test_a_bed_appears_once_the_hospital_records_one(net):
    net.put(
        "/api/patients/SHOW-GO-1/readiness",
        json={"kind": "bed", "party": "Tata Memorial Hospital, Mumbai", "status": "pending"},
    )

    kinds = [s["kind"] for s in net.get("/api/patients/SHOW-GO-1/guide").json()["stages"]]

    assert "bed" in kinds
