"""How a vendor gets paid, without the money ever passing through Saathi.

The family pays the vendor — the lodge, the cab, the pharmacy — directly, on a
UPI pay link the vendor's own payment gateway issued. Saathi asks the gateway
to make the link, hands the link to the family, and later hears from the
gateway that it was paid. It never holds the funds, never settles them and
never nets one payment against another, which is what keeps it outside the
RBI's payment-aggregator rules. Everything in this port follows from that:

- **The merchant account is the vendor's, and is passed in per call.** A
  `MerchantAccount` carries one vendor's gateway credentials. Adapters do not
  read keys from the environment or hold a default account, because there is no
  "Saathi account" for money to land in.
- **Amounts are integer paise, everywhere.** A float rupee amount is how ₹0.01
  goes missing in a family's budget. Where a gateway insists on rupees on the
  wire, the adapter converts at the boundary and nowhere else.
- **Nothing about the family goes to the gateway.** Amount, our reference and a
  short description. No name, no phone, no diagnosis.
- **A webhook with a bad signature is not an event.** `verify_webhook` returns
  `None` for it rather than raising, because an unsigned request is something a
  stranger can send, and the route answering it should neither crash nor tell
  them why.

Three adapters satisfy it: `adapters/payments/razorpay.py`,
`adapters/payments/cashfree.py` and `adapters/payments/fake.py`, the last being
what tests and local runs use.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class PaymentUnavailable(RuntimeError):
    """The gateway could not be reached, refused, or answered unreadably.

    Raised by an adapter, never swallowed inside one. A caller that cannot tell
    a failed link creation from a successful one would send a family a link
    that does not exist.
    """


class PayLinkStatus(StrEnum):
    """Where a pay link has got to, normalised across gateways.

    `PARTIALLY_PAID` is kept apart from `PAID` on purpose: a vendor who has
    been paid half has not been paid. `UNKNOWN` is a status this code has
    never seen, and is never read as paid.
    """

    CREATED = "created"
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class PaymentEventKind(StrEnum):
    """What a verified webhook says happened."""

    PAID = "paid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    #: Signed, genuine, and not something this code acts on — a partial
    #: payment, a refund, an event type added after this was written.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MerchantAccount:
    """One vendor's gateway credentials.

    Values are handed in by whoever stored them; an adapter never reads them
    from the environment. The secrets are excluded from `repr` so an account
    that ends up in a log line or a traceback does not take its keys with it.
    """

    #: Which adapter this account belongs to: "razorpay", "cashfree", "fake".
    provider: str
    key_id: str
    secret: str = field(repr=False)
    webhook_secret: str = field(repr=False)
    #: The vendor's own phone, for a gateway that insists on a contact for the
    #: link (Cashfree does). Never the family's.
    contact_phone: str = field(default="", repr=False)


@dataclass(frozen=True)
class PayLink:
    """A link a family can pay a vendor through."""

    #: The gateway's own id for the link; what `fetch` takes.
    id: str
    short_url: str
    amount_paise: int
    #: Ours. Unique per spend, and how a webhook finds its way back to it.
    reference_id: str
    status: PayLinkStatus


@dataclass(frozen=True)
class PaymentEvent:
    """A gateway webhook that passed signature verification.

    `provider_event_id` is what a receiver deduplicates on: gateways deliver
    at least once, and a payment recorded twice is a budget that lies.
    """

    provider_event_id: str
    link_id: str
    reference_id: str
    #: What the gateway says moved, in paise. Zero when the event carries no
    #: amount (an expiry, a cancellation).
    amount_paise: int
    kind: PaymentEventKind


class PaymentProvider(Protocol):
    """The seam. Make a link, read a link, believe a webhook — or don't."""

    name: str

    def create_link(
        self,
        account: MerchantAccount,
        *,
        amount_paise: int,
        reference_id: str,
        description: str,
        expire_by: datetime | None = None,
    ) -> PayLink:
        """Ask the vendor's gateway for a pay link. Raises `PaymentUnavailable`."""
        ...

    def verify_webhook(
        self,
        account: MerchantAccount,
        raw_body: bytes,
        headers: Mapping[str, str],
    ) -> PaymentEvent | None:
        """The event a correctly signed webhook carries, or None.

        None for a missing or wrong signature, and for a signed body that is
        not readable as an event. Never raises for anything a sender controls.
        """
        ...

    def fetch(self, account: MerchantAccount, link_id: str) -> PayLink:
        """Read a link's current state back. Raises `PaymentUnavailable`."""
        ...

    def close(self) -> None: ...


def require_paise(amount_paise: int) -> int:
    """Reject anything that is not a positive integer number of paise.

    `bool` is excluded explicitly because it is an `int` subclass, and `True`
    paise is a bug, not a payment.
    """
    if isinstance(amount_paise, bool) or not isinstance(amount_paise, int):
        raise TypeError(f"amount must be int paise, got {type(amount_paise).__name__}")
    if amount_paise <= 0:
        raise ValueError(f"amount must be positive, got {amount_paise} paise")
    return amount_paise
