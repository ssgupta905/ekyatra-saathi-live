"""A deterministic in-memory gateway, for tests and for running without one.

Links get sequential ids, nothing leaves the process, and `signed_webhook`
produces exactly what a real gateway would send so the receiving route is
exercised end to end — including its signature check. Signing is Razorpay's
scheme (hex HMAC-SHA256 of the raw body) under its own header name, so a fake
webhook can never be mistaken for, or accepted as, a real one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime

from ...ports.payments import (
    MerchantAccount,
    PayLink,
    PayLinkStatus,
    PaymentEvent,
    PaymentEventKind,
    PaymentUnavailable,
    require_paise,
)
from ._common import header, hmac_sha256, same

SIGNATURE_HEADER = "X-Fake-Signature"
EVENT_ID_HEADER = "X-Fake-Event-Id"

_LINK_STATUS = {
    PaymentEventKind.PAID: PayLinkStatus.PAID,
    PaymentEventKind.EXPIRED: PayLinkStatus.EXPIRED,
    PaymentEventKind.CANCELLED: PayLinkStatus.CANCELLED,
}


class FakePayments:
    name = "fake"

    def __init__(self, *, base_url: str = "https://pay.example.invalid") -> None:
        self._root = base_url.rstrip("/")
        self._links: dict[str, PayLink] = {}
        self._events = 0
        #: Every create_link call, so a test can assert what would have been sent.
        self.requests: list[dict[str, object]] = []

    def close(self) -> None:
        pass

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
        self.requests.append(
            {
                "account": account.key_id,
                "amount_paise": amount_paise,
                "reference_id": reference_id,
                "description": description,
                "expire_by": expire_by,
            }
        )
        link_id = f"fake_link_{len(self._links) + 1:04d}"
        link = PayLink(
            id=link_id,
            short_url=f"{self._root}/{link_id}",
            amount_paise=amount_paise,
            reference_id=reference_id,
            status=PayLinkStatus.CREATED,
        )
        self._links[link_id] = link
        return link

    def fetch(self, account: MerchantAccount, link_id: str) -> PayLink:
        try:
            return self._links[link_id]
        except KeyError:
            raise PaymentUnavailable(f"fake: no link {link_id}") from None

    def verify_webhook(
        self,
        account: MerchantAccount,
        raw_body: bytes,
        headers: Mapping[str, str],
    ) -> PaymentEvent | None:
        signature = header(headers, SIGNATURE_HEADER)
        if not signature or not account.webhook_secret:
            return None
        if not same(hmac_sha256(account.webhook_secret, raw_body).hex(), signature):
            return None
        try:
            body = json.loads(raw_body)
        except ValueError:
            return None
        if not isinstance(body, dict):
            return None
        try:
            kind = PaymentEventKind(str(body.get("kind", "")))
        except ValueError:
            kind = PaymentEventKind.UNKNOWN
        amount = body.get("amount_paise", 0)
        if not isinstance(amount, int) or isinstance(amount, bool):
            amount = 0
        return PaymentEvent(
            provider_event_id=header(headers, EVENT_ID_HEADER) or "",
            link_id=str(body.get("link_id", "")),
            reference_id=str(body.get("reference_id", "")),
            amount_paise=amount,
            kind=kind,
        )

    def signed_webhook(
        self,
        account: MerchantAccount,
        link_id: str,
        kind: PaymentEventKind | str = PaymentEventKind.PAID,
    ) -> tuple[bytes, dict[str, str]]:
        """Settle a link as a gateway would, and return the webhook it would send.

        Updates the link's status so `fetch` agrees with the webhook, then
        returns `(raw_body, headers)` signed with the account's webhook secret.
        """
        link = self.fetch(account, link_id)
        kind_value = kind.value if isinstance(kind, PaymentEventKind) else kind
        known = PaymentEventKind.__members__.get(kind_value.upper())
        if known in _LINK_STATUS:
            self._links[link_id] = replace(link, status=_LINK_STATUS[known])
        self._events += 1
        raw = json.dumps(
            {
                "kind": kind_value,
                "link_id": link.id,
                "reference_id": link.reference_id,
                "amount_paise": link.amount_paise if known is PaymentEventKind.PAID else 0,
            },
            sort_keys=True,
        ).encode()
        headers = {
            SIGNATURE_HEADER: hmac_sha256(account.webhook_secret, raw).hex(),
            EVENT_ID_HEADER: f"fake_evt_{self._events:04d}",
        }
        return raw, headers
