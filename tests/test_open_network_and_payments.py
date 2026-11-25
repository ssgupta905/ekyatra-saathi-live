"""The whole of it, wired: an open-network ride the family books, a vendor the family pays.

Runs on real records with the in-process demo network and the fake gateway —
every Beckn message signed and verified, every webhook signed and verified —
so what is proven here is the wiring, not the pretend seller.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from saathi.config import Settings, get_settings
from saathi.domain.enums import ReadinessKind, ReadinessStatus, Role
from saathi.domain.spends import SpendCategory, SpendSource, SpendStatus
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
    monkeypatch.setenv("SAATHI_RECORDS_URL", f"sqlite:///{tmp_path}/wired.db")
    monkeypatch.setenv("SAATHI_SEED_DEMO", "true")
    monkeypatch.setenv("SAATHI_NETWORK_PROVIDERS", "demo=demo")
    monkeypatch.setenv("SAATHI_PAYMENT_ACCOUNTS", "demo-pay=fake")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        container = client.app.state.container
        outbox = Outbox()
        container.identity._email_sender = outbox
        container.identity.add_user("neha", "Neha", Role.ADMIN, PASSWORD)
        token = client.post(
            "/api/auth/login", json={"username": "neha", "password": PASSWORD}
        ).json()["token"]
        staff = {"authorization": f"Bearer {token}"}
        loaded = client.post("/api/demo/cast", json={"emails": EMAILS}, headers=staff)
        assert loaded.status_code == 200
        # No map service in a test: two fixed points stand in for the district and the hospital.
        container.runner.network.geocode = lambda place: (25.31, 82.97)

        def family(email):
            client.post("/api/auth/otp/request", json={"email": email})
            signed = client.post(
                "/api/auth/otp/verify", json={"email": email, "code": outbox.codes[email]}
            ).json()["token"]
            return {"authorization": f"Bearer {signed}"}

        client.family = family
        client.staff = staff
        client.runner = container.runner
        client.world = container.world
        yield client
    get_settings.cache_clear()


def _ride(app, pid="DEMO-3"):
    return next(i for i in app.world.readiness_for(pid) if i.kind is ReadinessKind.TRANSPORT)


def _round(app):
    return app.portal.call(app.runner.settle_partners)


# ---------------------------------------------------------------- the open network


def test_a_ride_is_quoted_by_the_seller_and_waits_for_the_family_s_book(app):
    _round(app)

    ride = _ride(app)
    assert ride.status is ReadinessStatus.PENDING and ride.network_quote_id
    assert ride.network_order_id is None, "a quote books nothing"
    meena = app.family("meena@example.com")
    books = app.get("/api/patients/DEMO-3/kharcha", headers=meena).json()
    assert len(books["bookable"]) == 1
    assert books["bookable"][0]["amount_paise"] > 0, "the seller's own figure"


def test_booking_needs_the_family_to_agree_to_share_their_contact(app):
    _round(app)
    meena = app.family("meena@example.com")
    item_id = _ride(app).id

    refused = app.post(f"/api/patients/DEMO-3/book/{item_id}", json={}, headers=meena)

    assert refused.status_code == 409
    assert _ride(app).network_order_id is None


def test_the_family_s_book_assigns_a_driver_and_the_ride_is_ready(app):
    _round(app)
    meena = app.family("meena@example.com")
    item_id = _ride(app).id

    booked = app.post(
        f"/api/patients/DEMO-3/book/{item_id}", json={"share_contact": True}, headers=meena
    )

    assert booked.status_code == 200
    ride = _ride(app)
    assert ride.status is ReadinessStatus.READY and ride.network_order_id
    assert "booked with" in ride.detail
    again = app.post(
        f"/api/patients/DEMO-3/book/{item_id}", json={"share_contact": True}, headers=meena
    )
    assert again.json()["item"]["network_order_id"] == ride.network_order_id, "one car, not two"


def test_nobody_at_the_hospital_can_book_for_the_family(app):
    _round(app)

    staff_try = app.post(
        f"/api/patients/DEMO-3/book/{_ride(app).id}", json={"share_contact": True},
        headers=app.staff,
    )  # fmt: skip

    assert staff_try.status_code == 403


def test_a_ride_the_seller_calls_off_is_blocked_with_the_alternate(app):
    app.runner.network.providers["demo"].seller.mode = "cancel"
    _round(app)
    meena = app.family("meena@example.com")
    app.post(
        f"/api/patients/DEMO-3/book/{_ride(app).id}", json={"share_contact": True}, headers=meena
    )

    _round(app)

    ride = _ride(app)
    assert ride.status is ReadinessStatus.BLOCKED and ride.alternative_available


def test_a_network_that_never_answers_leaves_the_ride_unknown(app):
    app.runner.network.providers["demo"].seller.silent_on = {"search"}
    _round(app)

    assert _ride(app).status is ReadinessStatus.UNKNOWN


# ---------------------------------------------------------------- the vendor's own gateway


def _stay_quote(app):
    return app.runner.kharcha.from_provider(
        "DEMO-1",
        source=SpendSource.PROVIDER_QUOTE,
        source_ref="partner-quote:DEMO-1-stay:ho-oyo-parel",
        amount_paise=1_800_00,
        category=SpendCategory.STAY,
        status=SpendStatus.QUOTED,
        party="OYO, Parel",
        organisation_id="ho-oyo-parel",
    )


def test_the_family_pays_a_vendor_through_the_vendor_s_own_link_and_the_books_say_paid(app):
    quote = _stay_quote(app)
    anita = app.family("anita@example.com")
    assert [e["id"] for e in app.get(
        "/api/patients/DEMO-1/kharcha", headers=anita).json()["payable"]] == [quote.id]  # fmt: skip

    link = app.post(f"/api/patients/DEMO-1/kharcha/entries/{quote.id}/pay", headers=anita).json()

    assert link["pay_url"]
    gateway = app.runner.payments.gateways["demo-pay"]
    sent = gateway.provider.requests[-1]
    assert sent["amount_paise"] == 1_800_00 and sent["reference_id"] == quote.id
    assert "Anita" not in str(sent), "nothing about the family goes to the gateway"

    body, headers = gateway.provider.signed_webhook(gateway.account, link["entry"]["pay_link_id"])
    heard = app.post("/api/webhooks/payments/demo-pay", content=body, headers=headers)

    assert heard.json()["outcome"] == "paid"
    paid = app.runner.kharcha.store.get("DEMO-1", quote.id)
    assert paid.status is SpendStatus.PAID
    month = app.get("/api/patients/DEMO-1/kharcha", headers=anita).json()["months"][0]
    assert month["by_category"]["stay"] >= 1_800_00

    again = app.post("/api/webhooks/payments/demo-pay", content=body, headers=headers)
    # A gateway's second delivery is not a second payment.
    assert again.json()["outcome"] == "duplicate"


def test_a_webhook_that_does_not_verify_changes_nothing(app):
    quote = _stay_quote(app)
    anita = app.family("anita@example.com")
    link = app.post(f"/api/patients/DEMO-1/kharcha/entries/{quote.id}/pay", headers=anita).json()
    gateway = app.runner.payments.gateways["demo-pay"]
    body, headers = gateway.provider.signed_webhook(gateway.account, link["entry"]["pay_link_id"])

    forged = app.post(
        "/api/webhooks/payments/demo-pay", content=body.replace(b"paid", b"paid "), headers=headers
    )

    assert forged.status_code == 401
    assert app.runner.kharcha.store.get("DEMO-1", quote.id).status is SpendStatus.QUOTED


def test_a_pretend_network_or_gateway_is_refused_in_production():
    with pytest.raises(ValueError):
        Settings(environment="production", network_providers=["demo=demo"], _env_file=None)
    with pytest.raises(ValueError):
        Settings(environment="production", payment_accounts=["x=fake"], _env_file=None)
