"""Reaching organisations over an open network (Beckn/ONDC), the family deciding.

A LIVE organisation in the directory is not asked and then waited on, like a
dharamshala clerk in the partner app. It is searched and asked for a firm price
by the seller itself — committing nobody — and the price goes into the
family's books as that seller's quote. Nothing is booked until the family taps
Book, because booking dispatches a car and may cost them a cancellation fee:
it is their money, so it is their tap.

Every failure reads the same way the rest of the system reads silence: a
network that does not answer leaves the need UNKNOWN, which the planner turns
into UNCERTAIN. A booked ride the seller later calls off is BLOCKED, with the
directory's alternate if it has one — the same REPLAN a cab firm saying "no"
has always produced.

Quote and order handles live in the provider's memory. A restart between a
quote and the family's Book forgets the quote, and the next round simply asks
again; a restart after booking keeps the order id on the readiness item.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from ..domain.directory import Organisation, PartnerMode
from ..domain.enums import ReadinessKind, ReadinessStatus
from ..domain.models import ReadinessItem
from ..domain.spends import SpendSource, SpendStatus
from ..ports.network import (
    Fulfilment,
    GeoPoint,
    NetworkProvider,
    NetworkUnavailable,
    OrderState,
    QuoteChanged,
    SearchIntent,
)
from ..ports.registry import RegistryStore
from .kharcha import CATEGORY_FOR_NEED, KharchaDesk
from .world import LiveWorld

logger = logging.getLogger(__name__)

#: The open networks carry rides today. Hotels are a draft spec, and medicines
#: stay with partner pharmacies (prescription rules); neither is searched here.
SEARCHABLE = frozenset({ReadinessKind.TRANSPORT})


class NotBookable(ValueError):
    """There is no firm price waiting for this need, or it is already booked."""


def _quote_ref(quote_id: str) -> str:
    return f"network-quote:{quote_id}"


@dataclass
class NetworkDesk:
    providers: dict[str, NetworkProvider]
    world: LiveWorld
    registry: RegistryStore
    kharcha: KharchaDesk | None = None
    #: A place name to its coordinates, or None. Blocking; run in a thread.
    geocode: Callable[[str], tuple[float, float] | None] = lambda place: None
    _busy: set[str] = field(default_factory=set)

    # ---------------------------------------------------------------- reading

    def _org(self, item: ReadinessItem) -> Organisation | None:
        return next((o for o in self.registry.organisations() if o.id == item.partner_id), None)

    def _provider(self, org: Organisation | None) -> NetworkProvider | None:
        if org is None or org.mode is not PartnerMode.LIVE or not org.provider:
            return None
        return self.providers.get(org.provider)

    def _items(self):
        for patient in self.world.patients():
            for item in self.world.readiness_for(patient.id):
                org = self._org(item)
                provider = self._provider(org)
                if provider is not None:
                    yield patient, item, org, provider

    def bookable(self, patient_id: str) -> list[dict]:
        """Firm prices waiting for this family's tap, with the seller's own figure."""
        found = []
        for patient, item, org, _ in self._items():
            if patient.id != patient_id or not item.network_quote_id or item.network_order_id:
                continue
            entry = (
                self.kharcha.store.by_source(
                    SpendSource.PROVIDER_QUOTE, _quote_ref(item.network_quote_id)
                )
                if self.kharcha
                else None
            )
            found.append(
                {
                    "item_id": item.id,
                    "need": item.kind.value,
                    "provider": entry.party if entry and entry.party else org.name,
                    "amount_paise": entry.amount_paise if entry else None,
                    "entry_id": entry.id if entry else None,
                }
            )
        return found

    # ---------------------------------------------------------------- asking for a price

    async def _intent(self, patient, org: Organisation) -> SearchIntent | None:
        hospital = next((h for h in self.registry.hospitals() if h.id == patient.hospital_id), None)
        if hospital is None:
            return None
        start, end = await asyncio.gather(
            asyncio.to_thread(self.geocode, patient.home_district),
            asyncio.to_thread(self.geocode, hospital.place),
        )
        if start is None or end is None:
            return None
        return SearchIntent(pickup=GeoPoint(*start), drop=GeoPoint(*end))

    async def _quote(self, patient, item: ReadinessItem, org, provider) -> ReadinessItem:
        intent = await self._intent(patient, org)
        if intent is None:
            return self._unknown(item, "could not place the journey on a map")
        try:
            offers = await provider.search(intent)
            if not offers:
                return self._blocked(item, org, f"no {org.name} ride is on offer")
            quote = await provider.quote(offers[0].id)
        except NetworkUnavailable as exc:
            logger.info("network did not answer for %s: %s", item.id, exc)
            return self._unknown(item, f"no answer from {org.name}")

        if self.kharcha is not None and item.kind in CATEGORY_FOR_NEED:
            self.kharcha.from_provider(
                patient.id,
                source=SpendSource.PROVIDER_QUOTE,
                source_ref=_quote_ref(quote.id),
                amount_paise=quote.amount_paise,
                category=CATEGORY_FOR_NEED[item.kind],
                status=SpendStatus.QUOTED,
                party=quote.provider_name or org.name,
                organisation_id=org.id,
            )
        return self.world.set_readiness_item(
            item.model_copy(
                update={
                    "status": ReadinessStatus.PENDING,
                    "detail": f"{quote.provider_name or org.name} has quoted; tap Book to confirm",
                    "network_quote_id": quote.id,
                    # The seller has answered. Waiting on the family now, not on them.
                    "answer_by": None,
                    "due_at": None,
                }
            )
        )

    def _unknown(self, item: ReadinessItem, why: str) -> ReadinessItem:
        return self.world.set_readiness_item(
            item.model_copy(
                update={
                    "status": ReadinessStatus.UNKNOWN,
                    "detail": why,
                    "answer_by": None,
                    "network_quote_id": None,
                }
            )
        )

    def _blocked(self, item: ReadinessItem, org: Organisation, why: str) -> ReadinessItem:
        alternate = next(
            (o for o in self.registry.organisations() if o.id == org.alternate_id and o.active),
            None,
        )
        return self.world.set_readiness_item(
            item.model_copy(
                update={
                    "status": ReadinessStatus.BLOCKED,
                    "detail": why,
                    "alternative_available": alternate is not None,
                    "answer_by": None,
                    "network_quote_id": None,
                }
            )
        )

    # ---------------------------------------------------------------- the family's tap

    async def book(self, patient_id: str, item_id: str) -> ReadinessItem:
        """Book the quoted ride. The family's tap, and only theirs, gets here."""
        patient = self.world.patient(patient_id)
        found = next(
            ((i, o, p) for pt, i, o, p in self._items() if pt.id == patient_id and i.id == item_id),
            None,
        )
        if patient is None or found is None:
            raise NotBookable("nothing to book")
        item, org, provider = found
        if item.network_order_id:
            return item  # booking twice books one car
        if not item.network_quote_id:
            raise NotBookable("no price is waiting; ask again")

        who = Fulfilment(
            customer_name=(patient.name or "Saathi family").split(" ")[0],
            customer_phone=patient.caregiver_phone or "",
        )
        try:
            order = await provider.confirm(item.network_quote_id, who)
        except QuoteChanged:
            self._void_quote(patient_id, item.network_quote_id)
            return self.world.set_readiness_item(
                item.model_copy(
                    update={"detail": "the price changed; asking again", "network_quote_id": None}
                )
            )
        except NetworkUnavailable:
            # Not booked, as far as anyone can tell. The quote stays so the
            # family can try again; nothing is claimed.
            raise
        return self._from_order(item, org, order)

    def _void_quote(self, patient_id: str, quote_id: str) -> None:
        if self.kharcha is None:
            return
        entry = self.kharcha.store.by_source(SpendSource.PROVIDER_QUOTE, _quote_ref(quote_id))
        if entry is not None:
            self.kharcha.void(patient_id, entry.id)

    def _from_order(self, item: ReadinessItem, org: Organisation, order) -> ReadinessItem:
        if order.state in (OrderState.CONFIRMED, OrderState.IN_PROGRESS, OrderState.COMPLETED):
            vehicle = " · ".join(v for v in (order.driver_name, order.vehicle_registration) if v)
            update = {
                "status": ReadinessStatus.READY,
                "detail": f"booked with {order.provider_name or org.name}"
                + (f": {vehicle}" if vehicle else ""),
                "network_order_id": order.id,
            }
        elif order.state is OrderState.CANCELLED:
            return self._blocked(
                item, org, f"{order.provider_name or org.name} called the ride off"
            )
        else:
            update = {
                "status": ReadinessStatus.UNKNOWN,
                "detail": f"{org.name} has not said where the ride has got to",
                "network_order_id": order.id,
            }
        return self.world.set_readiness_item(item.model_copy(update=update))

    # ---------------------------------------------------------------- the round

    async def tick(self) -> list[str]:
        """Ask for prices that are missing, and follow booked rides. Families whose need changed."""
        changed: list[str] = []
        for patient, item, org, provider in list(self._items()):
            if item.id in self._busy:
                continue
            self._busy.add(item.id)
            try:
                before = (item.status, item.detail)
                if (
                    item.status is ReadinessStatus.PENDING
                    and not item.network_quote_id
                    and not item.network_order_id
                    and item.kind in SEARCHABLE
                ):
                    after = await self._quote(patient, item, org, provider)
                elif item.network_order_id and item.status is ReadinessStatus.READY:
                    try:
                        order = await provider.status(item.network_order_id)
                    except NetworkUnavailable:
                        continue  # a ride that was booked stays booked until someone says otherwise
                    after = self._from_order(item, org, order)
                    if order.state is OrderState.COMPLETED:
                        self._ask_family_to_confirm(patient.id, item)
                else:
                    continue
                if (after.status, after.detail) != before:
                    changed.append(patient.id)
            finally:
                self._busy.discard(item.id)
        return changed

    def _ask_family_to_confirm(self, patient_id: str, item: ReadinessItem) -> None:
        """The ride is done and the driver was paid directly. The family says it is right."""
        if self.kharcha is None or not item.network_quote_id:
            return
        entry = self.kharcha.store.by_source(
            SpendSource.PROVIDER_QUOTE, _quote_ref(item.network_quote_id)
        )
        if entry is not None and entry.status is SpendStatus.QUOTED:
            self.kharcha.store.save(entry.model_copy(update={"status": SpendStatus.PROPOSED}))

    async def close(self) -> None:
        for provider in self.providers.values():
            try:
                await provider.close()
            except Exception:  # noqa: BLE001 - closing one must not stop the rest
                logger.exception("could not close network %s", getattr(provider, "name", "?"))


__all__ = ["SEARCHABLE", "NetworkDesk", "NotBookable"]
