"""A Beckn buyer app (BAP) for ONDC mobility, behind `NetworkProvider`.

Beckn is asynchronous in a way HTTP clients are not used to. A request to a
seller (`/select`) is answered at once with only an acknowledgement; the real
answer arrives later as a separate, signed POST *to us* (`/on_select`), matched
to the request by `context.message_id`. So every call here is two halves:

1. sign and POST the request, and insist on an `ACK`;
2. wait for the callback that carries the same `message_id`, which the HTTP
   layer hands to `handle_callback`, which verifies it and wakes the waiter.

If the second half never comes, the call raises `NetworkUnavailable` after
`timeout` seconds. A search is the one exception to "one answer": any number
of sellers may answer it, so it collects for `search_window` seconds and
returns whatever arrived — and raises only if nothing did.

`handle_callback` trusts nothing it has not verified: the signature must check
out against the registry's key for the signer, the signer must be the seller
the context names, and the callback must answer a request we actually made to
that seller. A callback for a request we have stopped waiting for is
acknowledged (it is authentic) and kept in `unsolicited`, never acted on.

This adapter books nothing on its own. `quote()` is `/select` and nothing
more; only `confirm()` sends `/init` and `/confirm`, and it refuses if the
seller's final price is not the one quoted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ...ports.network import (
    Fulfilment,
    NetworkUnavailable,
    Offer,
    Order,
    Quote,
    QuoteChanged,
    SearchIntent,
)
from .context import build_context, new_id
from .mobility import CatalogItem, catalog_items, read_order, seller_quote
from .registry import SubscriberRegistry
from .signing import SignatureError, parse_header, sign_body, verify_body

logger = logging.getLogger(__name__)

ACK: dict = {"message": {"ack": {"status": "ACK"}}}


def nack(code: str, message: str) -> dict:
    return {
        "message": {"ack": {"status": "NACK"}},
        "error": {"type": "CONTEXT-ERROR", "code": code, "message": message},
    }


@dataclass(frozen=True)
class CallbackReply:
    """What the HTTP layer should answer a callback with."""

    status: int
    body: dict

    @property
    def acked(self) -> bool:
        message = self.body.get("message")
        ack = message.get("ack") if isinstance(message, dict) else None
        return self.status == 200 and isinstance(ack, dict) and ack.get("status") == "ACK"


@dataclass
class _Waiter:
    action: str
    #: The seller we asked, or "" for a broadcast search.
    bpp_id: str
    collect: bool
    future: asyncio.Future | None = None
    answers: list[tuple[dict, dict]] = field(default_factory=list)


@dataclass(frozen=True)
class _OfferRef:
    bpp_id: str
    bpp_uri: str
    transaction_id: str
    item: CatalogItem


@dataclass
class _QuoteRef:
    offer: _OfferRef
    quote: Quote
    order: Order | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class _OrderRef:
    bpp_id: str
    bpp_uri: str
    transaction_id: str
    quote_id: str
    provider_name: str


def _header(headers: Mapping[str, str], name: str) -> str:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return ""


class BecknProvider:
    """`NetworkProvider` over a Beckn network, as a buyer app."""

    name = "beckn"

    def __init__(
        self,
        *,
        bap_id: str,
        bap_uri: str,
        unique_key_id: str,
        private_key: Ed25519PrivateKey,
        registry: SubscriberRegistry,
        gateway_url: str,
        city_code: str,
        timeout: float = 15.0,
        search_window: float = 5.0,
        signature_ttl: int = 300,
        cancellation_reason_id: str = "0",
        client: httpx.AsyncClient | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.bap_id = bap_id
        self.bap_uri = bap_uri
        self._key_id = unique_key_id
        self._private_key = private_key
        self._registry = registry
        self._gateway = gateway_url
        self._city = city_code
        self._timeout = timeout
        self._search_window = search_window
        self._signature_ttl = signature_ttl
        self._cancel_reason = cancellation_reason_id
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._now = now
        self._waiters: dict[str, _Waiter] = {}
        self._offers: dict[str, _OfferRef] = {}
        self._quotes: dict[str, _QuoteRef] = {}
        self._orders: dict[str, _OrderRef] = {}
        #: Authentic callbacks that answered nothing we were waiting for.
        self.unsolicited: deque[dict] = deque(maxlen=100)

    @property
    def live(self) -> bool:
        return True

    # --- the port --------------------------------------------------------

    async def search(self, intent: SearchIntent) -> tuple[Offer, ...]:
        transaction_id = new_id()
        fulfillment: dict = {
            "stops": [
                {"type": "START", "location": {"gps": intent.pickup.gps()}},
                {"type": "END", "location": {"gps": intent.drop.gps()}},
            ]
        }
        if intent.vehicle_category:
            fulfillment["vehicle"] = {"category": intent.vehicle_category}
        message = {
            "intent": {
                "fulfillment": fulfillment,
                "payment": {"collected_by": "BPP"},
            }
        }
        context = self._context("search", transaction_id)
        answers = await self._exchange(self._gateway, context, message, collect=True)
        if not answers:
            raise NetworkUnavailable(
                f"no seller answered the search within {self._search_window}s"
            )

        offers: list[Offer] = []
        for reply_context, reply_message in answers:
            bpp_id = str(reply_context.get("bpp_id") or "")
            bpp_uri = str(reply_context.get("bpp_uri") or "")
            for item in catalog_items(reply_message):
                offer_id = new_id()
                self._offers[offer_id] = _OfferRef(bpp_id, bpp_uri, transaction_id, item)
                offers.append(
                    Offer(
                        id=offer_id,
                        network=bpp_id,
                        provider_name=item.provider_name,
                        item_name=item.item_name,
                        vehicle_category=item.vehicle_category,
                        estimated_paise=item.estimated_paise,
                        currency=item.currency,
                    )
                )
        return tuple(offers)

    async def quote(self, offer_id: str) -> Quote:
        """`/select`, and nothing else. Raises `KeyError` for an offer we never made."""
        ref = self._offers[offer_id]
        message = {"order": self._order_body(ref)}
        context = self._context("select", ref.transaction_id, ref.bpp_id, ref.bpp_uri)
        ((_, reply),) = await self._exchange(ref.bpp_uri, context, message, bpp_id=ref.bpp_id)
        priced = seller_quote(reply)
        quote = Quote(
            id=new_id(),
            offer_id=offer_id,
            provider_name=ref.item.provider_name,
            amount_paise=priced.amount_paise,
            currency=priced.currency,
            breakup=priced.breakup,
            valid_for=priced.valid_for,
        )
        self._quotes[quote.id] = _QuoteRef(offer=ref, quote=quote)
        return quote

    async def confirm(self, quote_id: str, fulfilment: Fulfilment) -> Order:
        """`/init` then `/confirm`. Idempotent per quote. Raises `KeyError` if unknown."""
        held = self._quotes[quote_id]
        async with held.lock:
            if held.order is not None:
                return held.order
            ref = held.offer
            order_body = self._order_body(ref)
            order_body["fulfillments"] = [
                {
                    **({"id": ref.item.fulfillment_id} if ref.item.fulfillment_id else {}),
                    "customer": {
                        "person": {"name": fulfilment.customer_name},
                        "contact": {"phone": fulfilment.customer_phone},
                    },
                }
            ]
            order_body["billing"] = {
                "name": fulfilment.customer_name,
                "phone": fulfilment.customer_phone,
            }
            order_body["payments"] = [
                {"collected_by": "BPP", "type": "ON-FULFILLMENT", "status": "NOT-PAID"}
            ]

            context = self._context("init", ref.transaction_id, ref.bpp_id, ref.bpp_uri)
            ((_, init_reply),) = await self._exchange(
                ref.bpp_uri, context, {"order": order_body}, bpp_id=ref.bpp_id
            )
            final = seller_quote(init_reply)
            quoted = held.quote
            if final.amount_paise != quoted.amount_paise or final.currency != quoted.currency:
                raise QuoteChanged(
                    f"{ref.item.provider_name} quoted {quoted.amount_paise} "
                    f"{quoted.currency} and now asks {final.amount_paise} {final.currency}",
                    quoted_paise=quoted.amount_paise,
                    offered_paise=final.amount_paise,
                )

            init_order = init_reply.get("order") or {}
            if isinstance(init_order.get("payments"), list):
                order_body["payments"] = init_order["payments"]
            order_body["quote"] = init_order.get("quote")

            context = self._context("confirm", ref.transaction_id, ref.bpp_id, ref.bpp_uri)
            ((_, confirm_reply),) = await self._exchange(
                ref.bpp_uri, context, {"order": order_body}, bpp_id=ref.bpp_id
            )
            order = read_order(
                confirm_reply, quote_id=quote_id, provider_name=ref.item.provider_name
            )
            self._orders[order.id] = _OrderRef(
                ref.bpp_id, ref.bpp_uri, ref.transaction_id, quote_id, ref.item.provider_name
            )
            held.order = order
            return order

    async def status(self, order_id: str) -> Order:
        """`/status`. Raises `KeyError` for an order this adapter did not place."""
        ref = self._orders[order_id]
        context = self._context("status", ref.transaction_id, ref.bpp_id, ref.bpp_uri)
        ((_, reply),) = await self._exchange(
            ref.bpp_uri, context, {"order_id": order_id}, bpp_id=ref.bpp_id
        )
        return read_order(reply, quote_id=ref.quote_id, provider_name=ref.provider_name)

    async def cancel(self, order_id: str, reason: str) -> Order:
        """`/cancel`. Raises `KeyError` for an order this adapter did not place."""
        ref = self._orders[order_id]
        context = self._context("cancel", ref.transaction_id, ref.bpp_id, ref.bpp_uri)
        message = {
            "order_id": order_id,
            "cancellation_reason_id": self._cancel_reason,
            "descriptor": {"code": "CONFIRM_CANCEL", "name": reason},
        }
        ((_, reply),) = await self._exchange(ref.bpp_uri, context, message, bpp_id=ref.bpp_id)
        return read_order(reply, quote_id=ref.quote_id, provider_name=ref.provider_name)

    async def close(self) -> None:
        for waiter in self._waiters.values():
            if waiter.future is not None and not waiter.future.done():
                waiter.future.set_exception(NetworkUnavailable("provider closed"))
        self._waiters.clear()
        if self._owns_client:
            await self._client.aclose()

    # --- callbacks -------------------------------------------------------

    async def handle_callback(
        self, action: str, raw_body: bytes, headers: Mapping[str, str]
    ) -> CallbackReply:
        """Verify one `on_*` POST and hand it to whoever is waiting for it.

        `raw_body` must be the bytes as received; the signature covers them.
        Returns what to answer with: 200 ACK, or a NACK with 400 (malformed or
        not ours), 401 (not provably from who it claims) or 503 (could not
        reach the registry to find out).
        """
        if not action.startswith("on_"):
            return CallbackReply(400, nack("10000", f"{action} is not a callback"))
        try:
            parsed = parse_header(_header(headers, "Authorization"))
        except SignatureError as exc:
            return CallbackReply(401, nack("10001", str(exc)))
        try:
            public_key = await self._registry.public_key(
                parsed.subscriber_id, parsed.unique_key_id
            )
            signer = verify_body(raw_body, parsed, public_key=public_key, now=self._now)
        except SignatureError as exc:
            return CallbackReply(401, nack("10001", str(exc)))
        except NetworkUnavailable as exc:
            return CallbackReply(503, nack("20000", str(exc)))

        try:
            payload = json.loads(raw_body)
            context = payload["context"]
            message_id = str(context["message_id"])
        except (ValueError, KeyError, TypeError):
            return CallbackReply(400, nack("10000", "body is not a Beckn message"))
        if not isinstance(context, dict):
            return CallbackReply(400, nack("10000", "context is not an object"))
        if context.get("action") != action:
            return CallbackReply(400, nack("10000", "context.action does not match the path"))
        if context.get("bap_id") != self.bap_id:
            return CallbackReply(400, nack("10000", "addressed to another buyer app"))
        if context.get("bpp_id") != signer.subscriber_id:
            return CallbackReply(401, nack("10001", "signer is not the seller in the context"))

        waiter = self._waiters.get(message_id)
        if waiter is None:
            self.unsolicited.append(payload)
            return CallbackReply(200, ACK)
        if waiter.action != action:
            return CallbackReply(400, nack("10000", f"expected {waiter.action}"))
        if waiter.bpp_id and waiter.bpp_id != signer.subscriber_id:
            return CallbackReply(400, nack("10000", "answer from a seller we did not ask"))

        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        error = payload.get("error")
        if waiter.collect:
            if not error:
                waiter.answers.append((context, message))
        elif waiter.future is not None and not waiter.future.done():
            if error:
                waiter.future.set_exception(
                    NetworkUnavailable(f"{signer.subscriber_id} answered {action} with {error}")
                )
            else:
                waiter.future.set_result((context, message))
        return CallbackReply(200, ACK)

    # --- plumbing --------------------------------------------------------

    def _context(
        self, action: str, transaction_id: str, bpp_id: str = "", bpp_uri: str = ""
    ) -> dict:
        return build_context(
            action=action,
            bap_id=self.bap_id,
            bap_uri=self.bap_uri,
            transaction_id=transaction_id,
            city_code=self._city,
            bpp_id=bpp_id,
            bpp_uri=bpp_uri,
            ttl=f"PT{max(1, int(self._timeout))}S",
        )

    @staticmethod
    def _order_body(ref: _OfferRef) -> dict:
        order: dict = {
            "provider": {"id": ref.item.provider_id},
            "items": [{"id": ref.item.item_id}],
        }
        if ref.item.fulfillment_id:
            order["fulfillments"] = [{"id": ref.item.fulfillment_id}]
        return order

    async def _exchange(
        self,
        url: str,
        context: dict,
        message: dict,
        *,
        bpp_id: str = "",
        collect: bool = False,
    ) -> list[tuple[dict, dict]]:
        """POST one signed request and wait for its callback(s)."""
        action = context["action"]
        message_id = context["message_id"]
        loop = asyncio.get_running_loop()
        waiter = _Waiter(
            action=f"on_{action}",
            bpp_id=bpp_id,
            collect=collect,
            future=None if collect else loop.create_future(),
        )
        # Registered before the POST: a seller may call back before its ACK lands.
        self._waiters[message_id] = waiter
        try:
            await self._post(url, action, {"context": context, "message": message})
            if collect:
                await asyncio.sleep(self._search_window)
                return list(waiter.answers)
            assert waiter.future is not None
            try:
                answer = await asyncio.wait_for(waiter.future, self._timeout)
            except TimeoutError as exc:
                raise NetworkUnavailable(
                    f"no {waiter.action} from {bpp_id or 'the network'} within {self._timeout}s"
                ) from exc
            return [answer]
        finally:
            self._waiters.pop(message_id, None)

    async def _post(self, url: str, action: str, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        authorization = sign_body(
            body,
            private_key=self._private_key,
            subscriber_id=self.bap_id,
            unique_key_id=self._key_id,
            ttl=self._signature_ttl,
            now=self._now,
        )
        try:
            response = await self._client.post(
                f"{url.rstrip('/')}/{action}",
                content=body,
                headers={"Content-Type": "application/json", "Authorization": authorization},
                timeout=self._timeout,
            )
            response.raise_for_status()
            reply = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise NetworkUnavailable(f"{action} to {url} failed: {exc}") from exc
        if not CallbackReply(200, reply if isinstance(reply, dict) else {}).acked:
            raise NetworkUnavailable(f"{action} to {url} was not acknowledged: {reply}")
