"""Razorpay Payment Links, on the vendor's own Razorpay account.

Create and fetch use `POST/GET /v1/payment_links` with HTTP basic auth (key id
and key secret). Webhooks are signed with HMAC-SHA256 over the raw body using
the webhook secret configured on the dashboard, sent hex-encoded in
`X-Razorpay-Signature`. The signature covers bytes, not parsed JSON, which is
why the receiver must hand over the body exactly as it arrived.

Razorpay notifications are turned off on every link: Saathi delivers the link
to the family itself, and asking Razorpay to SMS or email would mean sending it
the family's contact details.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime

import httpx

from ...ports.payments import (
    MerchantAccount,
    PayLink,
    PayLinkStatus,
    PaymentEvent,
    PaymentEventKind,
    PaymentUnavailable,
    require_paise,
)
from ._common import body_digest, header, hmac_sha256, same, send

BASE_URL = "https://api.razorpay.com"

_STATUS = {
    "created": PayLinkStatus.CREATED,
    "paid": PayLinkStatus.PAID,
    "partially_paid": PayLinkStatus.PARTIALLY_PAID,
    "expired": PayLinkStatus.EXPIRED,
    "cancelled": PayLinkStatus.CANCELLED,
}

_EVENTS = {
    "payment_link.paid": PaymentEventKind.PAID,
    "payment_link.expired": PaymentEventKind.EXPIRED,
    "payment_link.cancelled": PaymentEventKind.CANCELLED,
}


class RazorpayPayments:
    name = "razorpay"

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        upi_link: bool = False,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        """`upi_link=True` asks for a UPI-only link.

        Off by default because Razorpay does not support UPI links in test
        mode, and every account this code has seen is in test mode.
        """
        self._root = base_url.rstrip("/")
        self._upi_link = upi_link
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def create_link(
        self,
        account: MerchantAccount,
        *,
        amount_paise: int,
        reference_id: str,
        description: str,
        expire_by: datetime | None = None,
    ) -> PayLink:
        payload: dict[str, object] = {
            "amount": require_paise(amount_paise),
            "currency": "INR",
            "reference_id": reference_id,
            "description": description[:2048],
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
        }
        if expire_by is not None:
            payload["expire_by"] = int(expire_by.timestamp())
        if self._upi_link:
            payload["upi_link"] = True
        body = send(
            self._client,
            self.name,
            "POST",
            f"{self._root}/v1/payment_links",
            json=payload,
            auth=(account.key_id, account.secret),
        )
        return _link(body)

    def fetch(self, account: MerchantAccount, link_id: str) -> PayLink:
        body = send(
            self._client,
            self.name,
            "GET",
            f"{self._root}/v1/payment_links/{link_id}",
            auth=(account.key_id, account.secret),
        )
        return _link(body)

    def verify_webhook(
        self,
        account: MerchantAccount,
        raw_body: bytes,
        headers: Mapping[str, str],
    ) -> PaymentEvent | None:
        signature = header(headers, "X-Razorpay-Signature")
        if not signature or not account.webhook_secret:
            return None
        expected = hmac_sha256(account.webhook_secret, raw_body).hex()
        if not same(expected, signature.strip()):
            return None
        try:
            body = json.loads(raw_body)
        except ValueError:
            return None
        if not isinstance(body, dict):
            return None

        payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
        link = _entity(payload, "payment_link")
        payment = _entity(payload, "payment")
        kind = _EVENTS.get(str(body.get("event", "")), PaymentEventKind.UNKNOWN)
        amount = payment.get("amount") if kind is PaymentEventKind.PAID else 0
        if not isinstance(amount, int) or isinstance(amount, bool):
            amount = 0
        return PaymentEvent(
            provider_event_id=header(headers, "X-Razorpay-Event-Id") or body_digest(raw_body),
            link_id=str(link.get("id", "")),
            reference_id=str(link.get("reference_id", "")),
            amount_paise=amount,
            kind=kind,
        )


def _entity(payload: object, key: str) -> dict:
    if not isinstance(payload, dict):
        return {}
    wrapper = payload.get(key)
    if not isinstance(wrapper, dict):
        return {}
    entity = wrapper.get("entity")
    return entity if isinstance(entity, dict) else {}


def _link(body: dict) -> PayLink:
    amount = body.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise PaymentUnavailable(f"razorpay link amount {amount!r} is not int paise")
    link_id = body.get("id")
    short_url = body.get("short_url")
    if not isinstance(link_id, str) or not isinstance(short_url, str):
        raise PaymentUnavailable("razorpay link had no id or short_url")
    return PayLink(
        id=link_id,
        short_url=short_url,
        amount_paise=amount,
        reference_id=str(body.get("reference_id") or ""),
        status=_STATUS.get(str(body.get("status", "")), PayLinkStatus.UNKNOWN),
    )
