"""Cashfree Payment Links, on the vendor's own Cashfree account.

Create and fetch use `POST/GET /pg/links` with `x-client-id`,
`x-client-secret` and `x-api-version` headers. Webhooks are signed as
base64(HMAC-SHA256(timestamp + raw body)) with the account's secret, sent in
`x-webhook-signature` alongside `x-webhook-timestamp`.

Two Cashfree particulars:

- **Amounts are rupees on the wire.** Converted from and to integer paise in
  `_common`, exactly, and nowhere else.
- **`customer_details.customer_phone` is required by the API.** It is filled
  with the *vendor's* contact phone from `MerchantAccount.contact_phone`, never
  the family's, and the link is created with Cashfree notifications off so
  nobody is messaged at that number. An account without one is refused here,
  before the request, rather than by Cashfree after it.

`link_id` is ours to choose, so it is the reference id: one fewer id to map.

Replay protection on the timestamp is the receiver's job; it has a clock and
this adapter deliberately does not.
"""

from __future__ import annotations

import base64
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
from ._common import (
    body_digest,
    header,
    hmac_sha256,
    paise_from_rupees,
    rupees_for_wire,
    same,
    send,
)

SANDBOX_URL = "https://sandbox.cashfree.com"
PRODUCTION_URL = "https://api.cashfree.com"
API_VERSION = "2023-08-01"

_STATUS = {
    "ACTIVE": PayLinkStatus.CREATED,
    "PAID": PayLinkStatus.PAID,
    "PARTIALLY_PAID": PayLinkStatus.PARTIALLY_PAID,
    "EXPIRED": PayLinkStatus.EXPIRED,
    "CANCELLED": PayLinkStatus.CANCELLED,
}

#: Payment-link webhooks all arrive as one event type; the link's status in
#: the data says what happened.
_LINK_EVENT = "PAYMENT_LINK_EVENT"
_EVENTS = {
    "PAID": PaymentEventKind.PAID,
    "EXPIRED": PaymentEventKind.EXPIRED,
    "CANCELLED": PaymentEventKind.CANCELLED,
}


class CashfreePayments:
    name = "cashfree"

    def __init__(
        self,
        *,
        base_url: str = SANDBOX_URL,
        timeout: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._root = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def _headers(self, account: MerchantAccount) -> dict[str, str]:
        return {
            "x-client-id": account.key_id,
            "x-client-secret": account.secret,
            "x-api-version": API_VERSION,
        }

    def create_link(
        self,
        account: MerchantAccount,
        *,
        amount_paise: int,
        reference_id: str,
        description: str,
        expire_by: datetime | None = None,
    ) -> PayLink:
        require_paise(amount_paise)
        if not account.contact_phone:
            raise PaymentUnavailable(
                "cashfree needs the vendor's contact phone on the merchant account"
            )
        payload: dict[str, object] = {
            "link_id": reference_id,
            "link_amount": rupees_for_wire(amount_paise),
            "link_currency": "INR",
            "link_purpose": description[:500],
            "customer_details": {"customer_phone": account.contact_phone},
            "link_notify": {"send_sms": False, "send_email": False},
            "link_partial_payments": False,
        }
        if expire_by is not None:
            payload["link_expiry_time"] = expire_by.isoformat()
        body = send(
            self._client,
            self.name,
            "POST",
            f"{self._root}/pg/links",
            json=payload,
            headers=self._headers(account),
        )
        return _link(body)

    def fetch(self, account: MerchantAccount, link_id: str) -> PayLink:
        body = send(
            self._client,
            self.name,
            "GET",
            f"{self._root}/pg/links/{link_id}",
            headers=self._headers(account),
        )
        return _link(body)

    def verify_webhook(
        self,
        account: MerchantAccount,
        raw_body: bytes,
        headers: Mapping[str, str],
    ) -> PaymentEvent | None:
        signature = header(headers, "x-webhook-signature")
        timestamp = header(headers, "x-webhook-timestamp")
        if not signature or not timestamp or not account.webhook_secret:
            return None
        digest = hmac_sha256(account.webhook_secret, timestamp.encode() + raw_body)
        if not same(base64.b64encode(digest).decode(), signature.strip()):
            return None
        try:
            body = json.loads(raw_body)
        except ValueError:
            return None
        if not isinstance(body, dict):
            return None

        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        kind = PaymentEventKind.UNKNOWN
        if body.get("type") == _LINK_EVENT:
            kind = _EVENTS.get(str(data.get("link_status", "")), PaymentEventKind.UNKNOWN)
        amount = 0
        if kind is PaymentEventKind.PAID:
            try:
                amount = paise_from_rupees(data.get("link_amount_paid"))
            except PaymentUnavailable:
                # Signed but unreadable: not something to record as money.
                kind = PaymentEventKind.UNKNOWN
        link_id = str(data.get("link_id", ""))
        return PaymentEvent(
            provider_event_id=header(headers, "x-idempotency-key") or body_digest(raw_body),
            link_id=link_id,
            # link_id is the reference id by construction.
            reference_id=link_id,
            amount_paise=amount,
            kind=kind,
        )


def _link(body: dict) -> PayLink:
    link_id = body.get("link_id")
    url = body.get("link_url")
    if not isinstance(link_id, str) or not isinstance(url, str):
        raise PaymentUnavailable("cashfree link had no link_id or link_url")
    return PayLink(
        id=link_id,
        short_url=url,
        amount_paise=paise_from_rupees(body.get("link_amount")),
        reference_id=link_id,
        status=_STATUS.get(str(body.get("link_status", "")), PayLinkStatus.UNKNOWN),
    )
