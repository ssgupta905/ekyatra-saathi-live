"""Kharcha through the API: the family's own books, which only the family can open."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from saathi.config import get_settings
from saathi.domain.enums import AlertKind, Role
from saathi.domain.spends import SpendCategory, SpendSource, SpendStatus
from saathi.main import create_app

PASSWORD = "correct horse battery"


def _family(pid, email):
    return {
        "id": pid, "name": f"{pid} family", "home_district": "Gaya", "home_distance_km": 1010,
        "language": "hi", "caregiver_phone": f"+91 98000 {pid[-5:]}", "caregiver_email": email,
        "hospital_id": "TMH-MUM",
    }  # fmt: skip


class Outbox:
    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    def send(self, email: str, code: str) -> None:
        self.codes[email] = code


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("SAATHI_WORLD", "real")
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/kharcha.db")
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
        for pid, email in (("K-00001", "one@example.com"), ("K-00002", "two@example.com")):
            made = client.post("/api/patients", json=_family(pid, email), headers=client.staff)
            assert made.status_code == 201, made.text

        def sign_in(email):
            client.post("/api/auth/otp/request", json={"email": email})
            token = client.post(
                "/api/auth/otp/verify", json={"email": email, "code": outbox.codes[email]}
            ).json()["token"]
            return {"authorization": f"Bearer {token}"}

        client.family = sign_in("one@example.com")
        client.other = sign_in("two@example.com")
        client.desk = container.runner.kharcha
        client.container = container
        yield client
    get_settings.cache_clear()


URL = "/api/patients/K-00001/kharcha"


def _add(api, text):
    return api.post(f"{URL}/entries", json={"text": text}, headers=api.family).json()["entry"]


def test_the_family_says_a_spend_confirms_it_and_sees_it_counted(api):
    added = api.post(f"{URL}/entries", json={"text": "₹450 auto"}, headers=api.family)

    assert added.status_code == 200
    entry = added.json()["entry"]
    assert entry["status"] == "proposed" and entry["category"] == "travel"
    assert api.get(URL, headers=api.family).json()["months"][0]["spent_paise"] == 0

    api.post(f"{URL}/entries/{entry['id']}/confirm", headers=api.family)

    month = api.get(URL, headers=api.family).json()["months"][0]
    assert month["spent_paise"] == 45_000
    assert month["by_category"] == {"travel": 45_000}


def test_a_typed_amount_and_kind_need_no_reading(api):
    added = api.post(
        f"{URL}/entries", json={"amount": 120, "category": "food"}, headers=api.family
    ).json()["entry"]

    assert added["amount_paise"] == 12_000 and added["category"] == "food"
    assert added["stated_in"], "the family's typing is kept as their words"


def test_words_without_a_clear_amount_ask_to_type_it(api):
    unclear = api.post(f"{URL}/entries", json={"text": "2 autos 300"}, headers=api.family)
    assert unclear.status_code == 422


def test_nobody_at_the_hospital_can_open_a_family_s_books(api):
    assert api.get(URL, headers=api.staff).status_code == 403
    assert api.post(f"{URL}/entries", json={"amount": 5}, headers=api.staff).status_code == 403


def test_another_family_cannot_learn_these_books_exist(api):
    assert api.get(URL, headers=api.other).status_code == 404


def test_the_ledger_proves_the_entry_without_holding_the_figure(api):
    entry = _add(api, "lodge 2400")
    api.post(f"{URL}/entries/{entry['id']}/confirm", headers=api.family)

    claims = [e.claim for e in api.container.ledger.for_patient("K-00001")]
    spend_claims = [c for c in claims if "spend" in c]
    assert spend_claims
    assert not any(re.search(r"\d", c) for c in spend_claims), spend_claims


def test_a_month_over_what_the_family_said_tells_the_desk_once_and_with_no_figures(api):
    api.put(f"{URL}/limit", json={"amount": 300, "said": "300 se zyada nahi"}, headers=api.family)
    entry = _add(api, "train 3100")
    api.post(f"{URL}/entries/{entry['id']}/confirm", headers=api.family)
    again = _add(api, "auto 200")
    api.post(f"{URL}/entries/{again['id']}/confirm", headers=api.family)

    body = api.get(URL, headers=api.family).json()
    assert body["over_limit"] is True
    assert "over_what_you_said" in {n["kind"] for n in body["nudges"]}
    help_alerts = [
        a for a in api.container.runner.alerts
        if a.patient_id == "K-00001" and a.kind is AlertKind.NEEDS_HELP
    ]  # fmt: skip
    assert len(help_alerts) == 1, "once a month, not once a spend"
    assert not re.search(r"\d", help_alerts[0].detail), help_alerts[0].detail


def test_a_provider_figure_delivered_twice_is_one_spend_and_moves_from_quoted_to_paid(api):
    desk = api.desk
    common = dict(
        source=SpendSource.PAYMENT_WEBHOOK, source_ref="evt-1", amount_paise=25_000,
        category=SpendCategory.TRAVEL, party="Ola",
    )  # fmt: skip
    first = desk.from_provider("K-00001", status=SpendStatus.QUOTED, **common)
    again = desk.from_provider("K-00001", status=SpendStatus.QUOTED, **common)
    paid = desk.from_provider("K-00001", status=SpendStatus.PAID, **common)

    assert first.id == again.id == paid.id
    assert [e.status for e in desk.store.entries("K-00001")] == [SpendStatus.PAID]


def test_the_books_survive_a_restart(tmp_path, monkeypatch, api):
    api.post(f"{URL}/entries", json={"text": "food 90"}, headers=api.family)
    store = api.desk.store

    from saathi.adapters.spends import SqlSpendStore

    assert isinstance(store, SqlSpendStore)
    assert SqlSpendStore(get_settings().records_url).entries("K-00001")


# ---------------------------------------------------------------- the money stays out of the plan


def test_no_module_outside_the_books_reads_a_family_s_spends():
    root = Path(__file__).resolve().parent.parent / "backend" / "saathi"
    allowed = {
        "domain/spends.py",
        "ports/spends.py",
        "adapters/spends/memory.py",
        "adapters/spends/sql.py",
        "adapters/spends/__init__.py",
        "db/tables.py",
        "db/migrations/versions/0013_spends.py",
        "orchestrator/kharcha.py",
        "live/kharcha.py",
        # The two desks that write a provider's figure into the books.
        "live/network.py",
        "live/payments.py",
        "api/kharcha.py",
        # Reads only how much of the family's own monthly limit is free, to weigh routes for them.
        "api/trip.py",
        # Reads only whether a limit was stated, to put cheaper shops first.
        "api/nearby.py",
        "api/partner.py",
        "api/demo.py",
        "bootstrap/container.py",
        "bootstrap/demo_spends.py",
    }
    marks = ("SpendEntry", "SpendStore", "spend_entries", "runner.kharcha", "KharchaDesk")
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if str(path.relative_to(root)) not in allowed
        and any(mark in path.read_text() for mark in marks)
    ]

    assert offenders == [], f"a family's spends must stay out of: {offenders}"


def test_the_planner_never_sees_what_a_family_spends():
    root = Path(__file__).resolve().parent.parent / "backend" / "saathi"
    planning = [*root.joinpath("planner").rglob("*.py"), root / "orchestrator/rules.py",
                root / "domain/affordability.py", root / "guide/build.py"]  # fmt: skip
    readers = [str(p.relative_to(root)) for p in planning
               if "spends" in p.read_text() or "kharcha" in p.read_text()]  # fmt: skip

    assert readers == [], f"money must never move a clinical date: {readers}"
