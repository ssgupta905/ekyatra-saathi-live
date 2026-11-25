"""Paying a vendor through the vendor's own gateway, and hearing that it happened.

Saathi never holds money. A vendor that takes payment by link has its own
gateway account (`Organisation.payment_account`); when the family taps Pay on
a quote, the vendor's gateway makes the link, the family pays the vendor, and
the gateway's signed webhook tells Saathi it is done. The family's books then
say "paid", on the gateway's word — not on anybody's guess.

What leaves Saathi for the gateway is an amount, the entry's own id, and a
one-line description. Never the family's name, phone or anything about why
they are travelling.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from ..domain.enums import SourceSystem
from ..domain.spends import SpendEntry, SpendSource, SpendStatus
from ..ports.payments import (
    MerchantAccount,
    PaymentEventKind,
    PaymentProvider,
    PaymentUnavailable,
)
from ..ports.registry import RegistryStore
from .kharcha import KharchaDesk

logger = logging.getLogger(__name__)

#: How long a pay link stays open. Long enough to reach a phone with signal.
LINK_LIFETIME = timedelta(days=2)


class NotPayable(ValueError):
    """This amount cannot be paid by link: it is not a vendor's, or the vendor takes none."""


@dataclass
class Gateway:
    provider: PaymentProvider
    account: MerchantAccount


@dataclass
class PaymentsDesk:
    #: Payment account id -> the vendor's gateway.
    gateways: dict[str, Gateway]
    kharcha: KharchaDesk
    registry: RegistryStore
    _seen_events: set[str] = field(default_factory=set)

    def _account_for(self, entry: SpendEntry) -> str | None:
        org = next(
            (o for o in self.registry.organisations() if o.id == entry.organisation_id), None
        )
        account = org.payment_account if org else None
        return account if account in self.gateways else None

    def payable(self, entry: SpendEntry) -> bool:
        return (
            entry.status is SpendStatus.QUOTED
            and entry.source is SpendSource.PROVIDER_QUOTE
            and self._account_for(entry) is not None
        )

    def pay_link(self, patient_id: str, entry_id: str) -> SpendEntry:
        """The vendor's own link for this quote, made once and reused."""
        entry = self.kharcha.store.get(patient_id, entry_id)
        if entry is None:
            raise NotPayable("no such entry")
        if entry.pay_url and entry.status is SpendStatus.QUOTED:
            return entry
        account_id = self._account_for(entry)
        if not self.payable(entry) or account_id is None:
            raise NotPayable("this vendor does not take payment by link")
        gateway = self.gateways[account_id]
        link = gateway.provider.create_link(
            gateway.account,
            amount_paise=entry.amount_paise,
            reference_id=entry.id,
            description=f"Saathi: {entry.category.value}",
            expire_by=datetime.now(UTC) + LINK_LIFETIME,
        )
        return self.kharcha.store.save(
            entry.model_copy(
                update={
                    "pay_account": account_id,
                    "pay_link_id": link.id,
                    "pay_url": link.short_url,
                }
            )
        )

    def webhook(self, account_id: str, raw_body: bytes, headers: Mapping[str, str]) -> str:
        """Hear from a vendor's gateway. Returns what happened: 'paid', 'ignored', 'duplicate'.

        Raises `PermissionError` for anything not provably from that gateway, so
        the route can answer 401 and record nothing.
        """
        gateway = self.gateways.get(account_id)
        if gateway is None:
            raise PermissionError("no such account")
        event = gateway.provider.verify_webhook(gateway.account, raw_body, headers)
        if event is None:
            raise PermissionError("signature did not verify")

        key = event.provider_event_id or hashlib.sha256(raw_body).hexdigest()
        if key in self._seen_events:
            return "duplicate"
        self._seen_events.add(key)

        entry = self.kharcha.store.by_id(event.reference_id)
        if entry is None or entry.pay_link_id not in (None, event.link_id):
            logger.warning("payment event for an entry we did not make: %s", event.reference_id)
            return "ignored"
        if event.kind is PaymentEventKind.PAID:
            if entry.status is SpendStatus.PAID:
                return "duplicate"
            paid = self.kharcha.from_provider(
                entry.patient_id,
                source=SpendSource.PROVIDER_QUOTE,
                source_ref=entry.source_ref or entry.id,
                # What the gateway says moved is what was paid.
                amount_paise=event.amount_paise or entry.amount_paise,
                category=entry.category,
                status=SpendStatus.PAID,
                party=entry.party,
                organisation_id=entry.organisation_id,
            )
            self.kharcha.ledger.record_once(
                entry.patient_id,
                source=SourceSystem.PARTNER,
                source_record_id=f"payment:{key}",
                claim=f"{entry.party or 'a vendor'}'s gateway reported a payment received",
                metadata={"entry": paid.id},
            )
            return "paid"
        if event.kind in (PaymentEventKind.EXPIRED, PaymentEventKind.CANCELLED):
            self.kharcha.store.save(entry.model_copy(update={"pay_link_id": None, "pay_url": None}))
            return "ignored"
        return "ignored"

    def close(self) -> None:
        for gateway in self.gateways.values():
            try:
                gateway.provider.close()
            except Exception:  # noqa: BLE001
                logger.exception("could not close a payment gateway")


__all__ = ["Gateway", "NotPayable", "PaymentUnavailable", "PaymentsDesk"]
