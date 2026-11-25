"""Payment gateway adapters: request shapes, webhook signatures, paise.

No network: every gateway call goes through `httpx.MockTransport`. No real
keys: every secret here is a made-up test string.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import httpx
import pytest
from saathi.adapters.payments import CashfreePayments, FakePayments, RazorpayPayments
from saathi.ports.payments import (
    MerchantAccount,
    PayLinkStatus,
    PaymentEventKind,
    PaymentProvider,
    PaymentUnavailable,
)

EXPIRY = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)


def _account(provider: str, **kw: str) -> MerchantAccount:
    return MerchantAccount(
        provider=provider,
        key_id=kw.get("key_id", "test_key_id"),
        secret=kw.get("secret", "test_key_secret"),
        webhook_secret=kw.get("webhook_secret", "test_webhook_secret"),
        contact_phone=kw.get("contact_phone", "9000000000"),
    )


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_adapters_satisfy_the_port():
    providers: list[PaymentProvider] = [
        RazorpayPayments(client=_client(lambda r: httpx.Response(500))),
        CashfreePayments(client=_client(lambda r: httpx.Response(500))),
        FakePayments(),
    ]
    assert [p.name for p in providers] == ["razorpay", "cashfree", "fake"]


def test_secrets_stay_out_of_repr():
    text = repr(_account("razorpay"))
    assert "test_key_secret" not in text
    assert "test_webhook_secret" not in text
    assert "9000000000" not in text


# ---------------- Razorpay ----------------

def test_razorpay_create_link_request_shape():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "id": "plink_T1",
                "short_url": "https://rzp.io/i/T1",
                "amount": 125050,
                "reference_id": "spend_42",
                "status": "created",
            },
        )

    rp = RazorpayPayments(client=_client(handler), upi_link=True)
    link = rp.create_link(
        _account("razorpay"),
        amount_paise=125050,
        reference_id="spend_42",
        description="Lodge, 2 nights",
        expire_by=EXPIRY,
    )

    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == "https://api.razorpay.com/v1/payment_links"
    expected_auth = "Basic " + base64.b64encode(b"test_key_id:test_key_secret").decode()
    assert request.headers["authorization"] == expected_auth
    body = json.loads(request.content)
    assert body == {
        "amount": 125050,
        "currency": "INR",
        "reference_id": "spend_42",
        "description": "Lodge, 2 nights",
        "notify": {"sms": False, "email": False},
        "reminder_enable": False,
        "expire_by": int(EXPIRY.timestamp()),
        "upi_link": True,
    }
    # No family details: nothing but the fields above went out.
    assert "customer" not in body

    assert link.id == "plink_T1"
    assert link.short_url == "https://rzp.io/i/T1"
    assert link.amount_paise == 125050 and type(link.amount_paise) is int
    assert link.status is PayLinkStatus.CREATED


def test_razorpay_upi_link_is_off_by_default_and_fetch_reads_status():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"id": "plink_T1", "short_url": "u", "amount": 500, "status": "paid"},
        )

    rp = RazorpayPayments(client=_client(handler))
    rp.create_link(_account("razorpay"), amount_paise=500, reference_id="r", description="d")
    assert "upi_link" not in json.loads(seen[0].content)

    link = rp.fetch(_account("razorpay"), "plink_T1")
    assert seen[1].method == "GET"
    assert seen[1].url.path == "/v1/payment_links/plink_T1"
    assert link.status is PayLinkStatus.PAID


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"error": {"description": "bad key"}}),
        httpx.Response(200, text="<html>not json</html>"),
        httpx.Response(200, json=[1, 2]),
        httpx.Response(200, json={"id": "p", "short_url": "u", "amount": 12.5}),
    ],
)
def test_razorpay_failures_are_payment_unavailable(response):
    rp = RazorpayPayments(client=_client(lambda r: response))
    with pytest.raises(PaymentUnavailable):
        rp.create_link(_account("razorpay"), amount_paise=100, reference_id="r", description="d")


def test_razorpay_transport_error_is_payment_unavailable():
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    rp = RazorpayPayments(client=_client(handler))
    with pytest.raises(PaymentUnavailable) as caught:
        rp.fetch(_account("razorpay"), "plink_x")
    assert "test_key_secret" not in str(caught.value)


def _razorpay_webhook(event: str, secret: str = "test_webhook_secret") -> tuple[bytes, dict]:
    raw = json.dumps(
        {
            "event": event,
            "payload": {
                "payment_link": {
                    "entity": {"id": "plink_T1", "reference_id": "spend_42", "status": "paid"}
                },
                "payment": {"entity": {"id": "pay_9", "amount": 125050}},
            },
        }
    ).encode()
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"X-Razorpay-Signature": signature, "X-Razorpay-Event-Id": "evt_1"}


def test_razorpay_good_signature_is_a_paid_event():
    raw, headers = _razorpay_webhook("payment_link.paid")
    rp = RazorpayPayments(client=_client(lambda r: httpx.Response(500)))
    # Header casing varies by framework.
    lowered = {k.lower(): v for k, v in headers.items()}
    event = rp.verify_webhook(_account("razorpay"), raw, lowered)
    assert event is not None
    assert event.kind is PaymentEventKind.PAID
    assert event.provider_event_id == "evt_1"
    assert event.link_id == "plink_T1"
    assert event.reference_id == "spend_42"
    assert event.amount_paise == 125050 and type(event.amount_paise) is int


def test_razorpay_bad_signatures_are_none():
    rp = RazorpayPayments(client=_client(lambda r: httpx.Response(500)))
    account = _account("razorpay")
    raw, headers = _razorpay_webhook("payment_link.paid")

    tampered = raw.replace(b"125050", b"999999")
    assert rp.verify_webhook(account, tampered, headers) is None

    _, wrong = _razorpay_webhook("payment_link.paid", secret="someone_else")
    assert rp.verify_webhook(account, raw, wrong) is None

    assert rp.verify_webhook(account, raw, {}) is None
    assert rp.verify_webhook(_account("razorpay", webhook_secret=""), raw, headers) is None


def test_razorpay_unknown_event_is_kind_unknown():
    raw, headers = _razorpay_webhook("payment_link.partially_paid")
    rp = RazorpayPayments(client=_client(lambda r: httpx.Response(500)))
    event = rp.verify_webhook(_account("razorpay"), raw, headers)
    assert event is not None
    assert event.kind is PaymentEventKind.UNKNOWN
    assert event.amount_paise == 0


def test_razorpay_event_id_falls_back_to_body_digest():
    raw, headers = _razorpay_webhook("payment_link.expired")
    del headers["X-Razorpay-Event-Id"]
    rp = RazorpayPayments(client=_client(lambda r: httpx.Response(500)))
    event = rp.verify_webhook(_account("razorpay"), raw, headers)
    assert event is not None and event.kind is PaymentEventKind.EXPIRED
    assert event.provider_event_id == "sha256:" + hashlib.sha256(raw).hexdigest()


# ---------------- Cashfree ----------------

def test_cashfree_create_link_request_shape():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "cf_link_id": 7,
                "link_id": "spend_42",
                "link_url": "https://payments-test.cashfree.com/links/abc",
                "link_amount": 1250.5,
                "link_status": "ACTIVE",
            },
        )

    cf = CashfreePayments(client=_client(handler))
    link = cf.create_link(
        _account("cashfree"),
        amount_paise=125050,
        reference_id="spend_42",
        description="Lodge, 2 nights",
        expire_by=EXPIRY,
    )

    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == "https://sandbox.cashfree.com/pg/links"
    assert request.headers["x-client-id"] == "test_key_id"
    assert request.headers["x-client-secret"] == "test_key_secret"
    assert request.headers["x-api-version"] == "2023-08-01"
    assert "authorization" not in request.headers
    body = json.loads(request.content)
    assert body == {
        "link_id": "spend_42",
        "link_amount": 1250.5,
        "link_currency": "INR",
        "link_purpose": "Lodge, 2 nights",
        "customer_details": {"customer_phone": "9000000000"},
        "link_notify": {"send_sms": False, "send_email": False},
        "link_partial_payments": False,
        "link_expiry_time": EXPIRY.isoformat(),
    }

    assert link.id == "spend_42"
    assert link.reference_id == "spend_42"
    assert link.short_url.endswith("/links/abc")
    assert link.amount_paise == 125050 and type(link.amount_paise) is int
    assert link.status is PayLinkStatus.CREATED


@pytest.mark.parametrize("paise", [1, 10, 99, 100, 12345, 999_999_99, 1_00_00_000_01])
def test_cashfree_paise_round_trip_exactly(paise):
    seen: list[dict] = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200,
            json={"link_id": "r", "link_url": "u", "link_amount": body["link_amount"],
                  "link_status": "ACTIVE"},
        )

    cf = CashfreePayments(client=_client(handler))
    link = cf.create_link(_account("cashfree"), amount_paise=paise, reference_id="r",
                          description="d")
    assert link.amount_paise == paise and type(link.amount_paise) is int


def test_cashfree_refuses_without_vendor_contact_before_any_request():
    def handler(request):
        raise AssertionError("must not be called")

    cf = CashfreePayments(client=_client(handler))
    with pytest.raises(PaymentUnavailable):
        cf.create_link(_account("cashfree", contact_phone=""), amount_paise=100,
                       reference_id="r", description="d")


def test_cashfree_fetch_and_errors():
    def handler(request):
        if request.url.path == "/pg/links/gone":
            return httpx.Response(404, json={"message": "link not found"})
        return httpx.Response(
            200,
            json={"link_id": "spend_42", "link_url": "u", "link_amount": 10,
                  "link_status": "PAID"},
        )

    cf = CashfreePayments(client=_client(handler), base_url="https://api.cashfree.com")
    link = cf.fetch(_account("cashfree"), "spend_42")
    assert link.status is PayLinkStatus.PAID
    assert link.amount_paise == 1000
    with pytest.raises(PaymentUnavailable):
        cf.fetch(_account("cashfree"), "gone")


def _cashfree_webhook(status: str, *, type_: str = "PAYMENT_LINK_EVENT",
                      secret: str = "test_webhook_secret") -> tuple[bytes, dict]:
    raw = json.dumps(
        {
            "type": type_,
            "data": {
                "link_id": "spend_42",
                "link_status": status,
                "link_amount": 1250.5,
                "link_amount_paid": 1250.5,
            },
            "event_time": "2026-11-25T10:00:00+05:30",
        }
    ).encode()
    timestamp = "1764045000"
    digest = hmac.new(secret.encode(), timestamp.encode() + raw, hashlib.sha256).digest()
    return raw, {
        "x-webhook-signature": base64.b64encode(digest).decode(),
        "x-webhook-timestamp": timestamp,
        "x-idempotency-key": "cf_evt_1",
    }


def test_cashfree_good_signature_is_a_paid_event():
    raw, headers = _cashfree_webhook("PAID")
    cf = CashfreePayments(client=_client(lambda r: httpx.Response(500)))
    event = cf.verify_webhook(_account("cashfree"), raw, headers)
    assert event is not None
    assert event.kind is PaymentEventKind.PAID
    assert event.provider_event_id == "cf_evt_1"
    assert event.link_id == event.reference_id == "spend_42"
    assert event.amount_paise == 125050 and type(event.amount_paise) is int


def test_cashfree_bad_signatures_are_none():
    cf = CashfreePayments(client=_client(lambda r: httpx.Response(500)))
    account = _account("cashfree")
    raw, headers = _cashfree_webhook("PAID")

    assert cf.verify_webhook(account, raw.replace(b"1250.5", b"9999.0"), headers) is None
    # The timestamp is signed too.
    assert cf.verify_webhook(account, raw, {**headers, "x-webhook-timestamp": "1"}) is None
    _, wrong = _cashfree_webhook("PAID", secret="someone_else")
    assert cf.verify_webhook(account, raw, wrong) is None
    missing = {k: v for k, v in headers.items() if k != "x-webhook-signature"}
    assert cf.verify_webhook(account, raw, missing) is None
    no_ts = {k: v for k, v in headers.items() if k != "x-webhook-timestamp"}
    assert cf.verify_webhook(account, raw, no_ts) is None


@pytest.mark.parametrize(
    ("status", "type_", "kind"),
    [
        ("EXPIRED", "PAYMENT_LINK_EVENT", PaymentEventKind.EXPIRED),
        ("CANCELLED", "PAYMENT_LINK_EVENT", PaymentEventKind.CANCELLED),
        ("PARTIALLY_PAID", "PAYMENT_LINK_EVENT", PaymentEventKind.UNKNOWN),
        ("PAID", "REFUND_STATUS_WEBHOOK", PaymentEventKind.UNKNOWN),
    ],
)
def test_cashfree_event_kinds(status, type_, kind):
    raw, headers = _cashfree_webhook(status, type_=type_)
    cf = CashfreePayments(client=_client(lambda r: httpx.Response(500)))
    event = cf.verify_webhook(_account("cashfree"), raw, headers)
    assert event is not None and event.kind is kind
    assert event.amount_paise == 0


# ---------------- amounts ----------------

@pytest.mark.parametrize("bad", [12.5, 100.0, "100", True, 0, -5])
def test_amounts_must_be_positive_int_paise(bad):
    for provider in (
        RazorpayPayments(client=_client(lambda r: httpx.Response(500))),
        CashfreePayments(client=_client(lambda r: httpx.Response(500))),
        FakePayments(),
    ):
        with pytest.raises((TypeError, ValueError)):
            provider.create_link(_account(provider.name), amount_paise=bad,
                                 reference_id="r", description="d")


# ---------------- fake ----------------

def test_fake_round_trip():
    fake = FakePayments()
    account = _account("fake")
    link = fake.create_link(account, amount_paise=49900, reference_id="spend_7",
                            description="Pharmacy")
    assert link.id == "fake_link_0001"
    assert link.status is PayLinkStatus.CREATED
    assert fake.requests[0]["amount_paise"] == 49900

    raw, headers = fake.signed_webhook(account, link.id)
    event = fake.verify_webhook(account, raw, headers)
    assert event is not None
    assert event.kind is PaymentEventKind.PAID
    assert event.reference_id == "spend_7"
    assert event.amount_paise == 49900
    assert event.provider_event_id == "fake_evt_0001"
    assert fake.fetch(account, link.id).status is PayLinkStatus.PAID

    # Deterministic: a fresh fake issues the same ids.
    again = FakePayments().create_link(account, amount_paise=1, reference_id="x",
                                       description="d")
    assert again.id == "fake_link_0001"


def test_fake_rejects_tampering_and_unknown_links():
    fake = FakePayments()
    account = _account("fake")
    link = fake.create_link(account, amount_paise=100, reference_id="r", description="d")
    raw, headers = fake.signed_webhook(account, link.id)
    assert fake.verify_webhook(account, raw.replace(b"100", b"900"), headers) is None
    assert fake.verify_webhook(_account("fake", webhook_secret="other"), raw, headers) is None
    assert fake.verify_webhook(account, raw, {}) is None
    with pytest.raises(PaymentUnavailable):
        fake.fetch(account, "nope")

    raw, headers = fake.signed_webhook(account, link.id, "refund.processed")
    event = fake.verify_webhook(account, raw, headers)
    assert event is not None and event.kind is PaymentEventKind.UNKNOWN
