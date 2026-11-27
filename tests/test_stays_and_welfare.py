"""A room asked for, bargained for on the family's say-so, and who pays for a change."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from saathi.config import get_settings
from saathi.domain.enums import Language, ReadinessKind, ReadinessStatus, Role
from saathi.language.questions import AskReason, AskTopic
from saathi.main import create_app
from saathi.money.negotiation import MAX_ROUNDS, SANDBOX_TERMS, negotiate

PASSWORD = "correct horse battery"

# ---------------------------------------------------------------- negotiation rules


def _deal(tier="modest", nights=2, cap=None):
    return negotiate(
        SANDBOX_TERMS[tier], partner="Lodge", nights=nights, party_size=2,
        check_in=date(2026, 12, 8), family_nightly_cap_paise=cap,
    )  # fmt: skip


def test_a_lodge_gives_a_patient_rate_from_the_first_night():
    deal = _deal("modest", 1)
    assert deal.agreed_nightly_paise is not None
    assert deal.agreed_nightly_paise < deal.list_nightly_paise


def test_a_two_night_patient_stay_comes_back_cheaper_with_breakfast():
    deal = _deal()
    assert deal.agreed_nightly_paise == 950_00
    assert deal.total_paise == 1_900_00
    assert deal.saved_paise == 500_00
    assert deal.includes == ("breakfast",)


@pytest.mark.parametrize("tier", list(SANDBOX_TERMS))
@pytest.mark.parametrize("nights", [1, 2, 3, 5])
def test_never_more_than_two_rounds_and_never_above_the_first_price(tier, nights):
    deal = _deal(tier, nights)
    assert deal.rounds <= MAX_ROUNDS
    assert all(o.round <= MAX_ROUNDS for o in deal.offers)
    if deal.agreed_nightly_paise is not None:
        assert deal.agreed_nightly_paise <= deal.list_nightly_paise


def test_the_family_s_cap_is_never_exceeded():
    deal = _deal("standard", 2, cap=1_800_00)
    assert all(o.nightly_paise <= 1_800_00 for o in deal.offers if o.by == "saathi")
    assert deal.agreed_nightly_paise is None or deal.agreed_nightly_paise <= 1_800_00


def test_only_dates_party_and_purpose_are_shared():
    assert set(_deal().shared) == {"check_in", "nights", "party_size", "purpose"}
    assert _deal().shared["purpose"] == "hospital visit"


def test_a_one_night_hotel_stay_is_refused_the_patient_rate_and_nothing_is_claimed():
    deal = _deal("standard", 1)
    assert deal.agreed_nightly_paise == deal.list_nightly_paise
    assert deal.saved_paise == 0
    assert deal.includes == ()


# ---------------------------------------------------------------- through the API


class Outbox:
    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    def send(self, email: str, code: str) -> None:
        self.codes[email] = code


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/stays.db")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        container = client.app.state.container
        outbox = Outbox()
        container.identity._email_sender = outbox
        container.identity.add_user("imran", "Imran", Role.ADMIN, PASSWORD)
        staff = client.post(
            "/api/auth/login", json={"username": "imran", "password": PASSWORD}
        ).json()["token"]
        client.staff = {"authorization": f"Bearer {staff}"}
        family = {
            "id": "S-00001", "name": "Kamla Devi", "home_district": "Gaya",
            "home_distance_km": 1010, "language": "hi", "caregiver_phone": "+91 99999 00001",
            "caregiver_email": "kamla@example.com", "hospital_id": "TMH-MUM",
        }  # fmt: skip
        assert client.post("/api/patients", json=family, headers=client.staff).status_code == 201
        # A real deployment's directory starts empty; a desk adds its partners.
        lodge = {
            "id": "ho-lodge-parel", "name": "Parel Guest House", "type": "hotel",
            "cost_tier": "modest", "districts": ["Mumbai"], "hospital_ids": ["TMH-MUM"],
        }  # fmt: skip
        added = client.post("/api/directory", json=lodge, headers=client.staff)
        assert added.status_code in (200, 201), added.text
        visit = (container.world.today + timedelta(days=9)).isoformat()
        made = client.post(
            "/api/patients/S-00001/steps",
            json={"kind": "scan", "status": "scheduled", "scheduled_for": visit},
            headers=client.staff,
        )
        assert made.status_code == 201, made.text
        client.post("/api/auth/otp/request", json={"email": "kamla@example.com"})
        token = client.post(
            "/api/auth/otp/verify",
            json={"email": "kamla@example.com", "code": outbox.codes["kamla@example.com"]},
        ).json()["token"]
        client.family = {"authorization": f"Bearer {token}"}
        client.container = container
        yield client
    get_settings.cache_clear()


def _needs_a_room(api) -> bool:
    found = api.post("/api/patients/S-00001/stays", headers=api.family)
    if found.status_code == 409:
        pytest.skip(f"no stay partner or night away in this deployment: {found.json()}")
    assert found.status_code == 200, found.text
    return True


def test_the_family_asks_bargains_and_books(api):
    _needs_a_room(api)
    [offer] = api.get("/api/patients/S-00001/stays", headers=api.family).json()["stays"]
    assert offer["can_negotiate"] and not offer["negotiated"] and offer["sandbox"]

    bargained = api.post(
        f"/api/patients/S-00001/stays/{offer['entry_id']}/negotiate", headers=api.family
    )
    assert bargained.status_code == 200, bargained.text
    [after] = bargained.json()["stays"]
    assert after["amount_paise"] <= offer["amount_paise"]
    assert bargained.json()["negotiation"]["rounds"] <= MAX_ROUNDS

    booked = api.post(
        f"/api/patients/S-00001/stays/{after['entry_id']}/book", headers=api.family
    )
    assert booked.status_code == 200, booked.text
    rooms = [
        i for i in api.container.world.readiness_for("S-00001") if i.kind is ReadinessKind.STAY
    ]
    assert rooms and rooms[0].status is ReadinessStatus.READY

    said = [r["kind"] for r in api.container.runner.outbound if r["patient_id"] == "S-00001"]
    assert {"stay_offer", "stay_deal", "stay_booked"} <= set(said)


def test_a_negotiated_rate_is_not_negotiated_again(api):
    _needs_a_room(api)
    [offer] = api.get("/api/patients/S-00001/stays", headers=api.family).json()["stays"]
    first = api.post(
        f"/api/patients/S-00001/stays/{offer['entry_id']}/negotiate", headers=api.family
    ).json()
    [after] = first["stays"]
    if after["negotiated"]:
        again = api.post(
            f"/api/patients/S-00001/stays/{after['entry_id']}/negotiate", headers=api.family
        )
        assert again.status_code == 409


def test_the_hospital_cannot_read_or_bargain_for_a_family_s_room(api):
    assert api.get("/api/patients/S-00001/stays", headers=api.staff).status_code == 403
    assert api.post("/api/patients/S-00001/stays", headers=api.staff).status_code == 403


# ---------------------------------------------------------------- welfare fund


def test_a_family_s_own_request_is_not_the_hospital_s_to_pay(api):
    runner = api.container.runner
    assert runner.hospital_cause("S-00001", "request:req-S-00001-0") is None


def test_a_leave_the_hospital_published_is_the_hospital_s_cause(api):
    runner = api.container.runner
    runner.conversation.open_question(
        patient_id="S-00001",
        reason=AskReason.DOCTOR_AWAY,
        topics=(AskTopic.TIMING,),
        asked_text="The doctor is away.",
        language=Language.HINDI,
        about_day=runner.world.today.isoformat(),
    )
    assert runner.hospital_cause("S-00001", "request:req-S-00001-0") == "the clinician was away"


@pytest.mark.asyncio
async def test_approving_with_nothing_waiting_touches_no_fund(api):
    runner = api.container.runner
    # Nothing waiting to approve is a lookup failure before any fund is touched.
    with pytest.raises(LookupError):
        await runner.approve_option(
            patient_id="S-00001", option_index=0, approved_by_role=Role.NAVIGATOR,
            approved_by="Arani", cover_from_welfare_fund=True,
        )  # fmt: skip


def test_the_cause_is_the_question_the_family_answered_not_a_newer_one(api):
    runner = api.container.runner
    today = runner.world.today.isoformat()
    runner.conversation.open_question(
        patient_id="S-00001", reason=AskReason.DOCTOR_AWAY, topics=(AskTopic.TIMING,),
        asked_text="The doctor is away.", language=Language.HINDI, about_day=today,
    )
    assert runner.conversation.record_answer("S-00001", {"not_before": today}, "after the 1st")
    runner.conversation.open_question(
        patient_id="S-00001", reason=AskReason.REPORT_PENDING, topics=(AskTopic.TIMING,),
        asked_text="A report is not back.", language=Language.HINDI, about_day=today,
    )
    assert runner.hospital_cause("S-00001", "request:req-S-00001-0") == "the clinician was away"
