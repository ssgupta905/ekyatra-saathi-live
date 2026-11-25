"""An in-process seller app (BPP) for ONDC mobility, for tests and demos.

It plays both the gateway and one seller: it takes the buyer app's signed
requests as an `httpx.MockTransport`, verifies them against the registry like a
real seller would, acknowledges, and then — on its own schedule — calls back
with a signed `on_*` through `deliver`, which is normally the buyer's
`handle_callback`. No sockets are opened.

It can be told to misbehave in the ways real sellers do:

- `mode="late"`: answer every request, `delay` seconds later.
- `mode="never"`: acknowledge every request and never call back.
- `mode="cancel"`: confirm the ride, then report it cancelled on `/status`.
- `silent_on`: never call back for just these actions.
- `fulfilment_state`: the state word `/status` reports (try one nobody knows).
- `init_fare`: a different final price on `/init` than was quoted on `/select`.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Literal

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .context import timestamp
from .registry import SubscriberRegistry
from .signing import SignatureError, parse_header, sign_body, verify_body

Deliver = Callable[[str, bytes, dict[str, str]], Awaitable[object]]
Mode = Literal["prompt", "late", "never", "cancel"]

_ACK = {"message": {"ack": {"status": "ACK"}}}

#: (item id, name, vehicle category, catalogue estimate)
_CATALOGUE = (
    ("auto-1", "Auto rickshaw", "AUTO_RICKSHAW", "92.00"),
    ("cab-1", "Hatchback cab", "CAB", "145.50"),
)

#: The firm fares `/select` quotes, as (title, value) breakup lines.
_FARES: dict[str, tuple[tuple[str, str], ...]] = {
    "auto-1": (("BASE_FARE", "30.00"), ("DISTANCE_FARE", "64.00")),
    "cab-1": (("BASE_FARE", "50.00"), ("DISTANCE_FARE", "95.50")),
}


def _total(item_id: str) -> str:
    return f"{sum(float(v) for _, v in _FARES[item_id]):.2f}"


class FakeBpp:
    def __init__(
        self,
        *,
        bpp_id: str,
        bpp_uri: str,
        unique_key_id: str,
        private_key: Ed25519PrivateKey,
        registry: SubscriberRegistry,
        deliver: Deliver | None = None,
        mode: Mode = "prompt",
        delay: float = 0.0,
        silent_on: frozenset[str] | set[str] = frozenset(),
        fulfilment_state: str = "RIDE_ASSIGNED",
        init_fare: str | None = None,
        provider_name: str = "Fake Cabs",
        now: Callable[[], float] = time.time,
    ) -> None:
        self.bpp_id = bpp_id
        self.bpp_uri = bpp_uri
        self._key_id = unique_key_id
        self._private_key = private_key
        self._registry = registry
        self.deliver = deliver
        self.mode = mode
        self.delay = delay
        self.silent_on = set(silent_on)
        self.fulfilment_state = fulfilment_state
        self.init_fare = init_fare
        self.provider_name = provider_name
        self._now = now
        #: Every request that verified, as (action, payload), in arrival order.
        self.received: list[tuple[str, dict]] = []
        #: What `deliver` returned for each callback.
        self.replies: list[object] = []
        self.orders: dict[str, dict] = {}
        self._tasks: set[asyncio.Task] = set()

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def actions(self) -> list[str]:
        return [action for action, _ in self.received]

    async def handle(self, request: httpx.Request) -> httpx.Response:
        action = request.url.path.rstrip("/").rsplit("/", 1)[-1]
        body = await request.aread()
        try:
            parsed = parse_header(request.headers.get("Authorization", ""))
            key = await self._registry.public_key(parsed.subscriber_id, parsed.unique_key_id)
            verify_body(body, parsed, public_key=key, now=self._now)
        except SignatureError as exc:
            return httpx.Response(
                401,
                json={"message": {"ack": {"status": "NACK"}}, "error": {"message": str(exc)}},
            )
        payload = json.loads(body)
        self.received.append((action, payload))
        if self.mode != "never" and action not in self.silent_on:
            task = asyncio.create_task(self._answer(action, payload))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return httpx.Response(200, json=_ACK)

    async def aclose(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    # --- answers ---------------------------------------------------------

    async def _answer(self, action: str, payload: dict) -> None:
        if self.mode == "late" and self.delay:
            await asyncio.sleep(self.delay)
        else:
            await asyncio.sleep(0)
        build = getattr(self, f"_on_{action}", None)
        if build is None or self.deliver is None:
            return
        message = build(payload["message"])
        context = dict(payload["context"])
        context.update(
            action=f"on_{action}",
            bpp_id=self.bpp_id,
            bpp_uri=self.bpp_uri,
            timestamp=timestamp(),
        )
        body = json.dumps({"context": context, "message": message}).encode()
        header = sign_body(
            body,
            private_key=self._private_key,
            subscriber_id=self.bpp_id,
            unique_key_id=self._key_id,
            now=self._now,
        )
        self.replies.append(await self.deliver(f"on_{action}", body, {"Authorization": header}))

    def _provider(self) -> dict:
        return {"id": "fake-cabs", "descriptor": {"name": self.provider_name}}

    def _on_search(self, message: dict) -> dict:
        wanted = (
            message.get("intent", {}).get("fulfillment", {}).get("vehicle", {}).get("category")
        )
        items, fulfilments = [], []
        for item_id, name, category, estimate in _CATALOGUE:
            if wanted and wanted != category:
                continue
            items.append(
                {
                    "id": item_id,
                    "descriptor": {"name": name, "code": "RIDE"},
                    "price": {"currency": "INR", "value": estimate},
                    "fulfillment_ids": [f"f-{item_id}"],
                }
            )
            fulfilments.append(
                {"id": f"f-{item_id}", "type": "DELIVERY", "vehicle": {"category": category}}
            )
        provider = {**self._provider(), "items": items, "fulfillments": fulfilments}
        return {"catalog": {"descriptor": {"name": "Fake mobility"}, "providers": [provider]}}

    def _quote(self, item_id: str, total: str | None = None) -> dict:
        return {
            "price": {"currency": "INR", "value": total or _total(item_id)},
            "breakup": [
                {"title": title, "price": {"currency": "INR", "value": value}}
                for title, value in _FARES[item_id]
            ],
            "ttl": "PT2M",
        }

    def _item(self, message: dict) -> str:
        return message["order"]["items"][0]["id"]

    def _on_select(self, message: dict) -> dict:
        item_id = self._item(message)
        order = {**message["order"], "provider": self._provider(), "quote": self._quote(item_id)}
        return {"order": order}

    def _on_init(self, message: dict) -> dict:
        item_id = self._item(message)
        order = {
            **message["order"],
            "provider": self._provider(),
            "quote": self._quote(item_id, self.init_fare),
            "payments": [
                {
                    "id": "pay-1",
                    "collected_by": "BPP",
                    "type": "ON-FULFILLMENT",
                    "status": "NOT-PAID",
                }
            ],
        }
        return {"order": order}

    def _ride(self, order: dict, *, status: str, state: str) -> dict:
        fulfilment = {
            **(order.get("fulfillments") or [{}])[0],
            "state": {"descriptor": {"code": state}},
            "agent": {"person": {"name": "Ramesh K"}},
            "vehicle": {"category": "CAB", "registration": "KA01AB1234"},
            "stops": [
                {"type": "START", "authorization": {"type": "OTP", "token": "4821"}},
                {"type": "END"},
            ],
        }
        return {**order, "status": status, "fulfillments": [fulfilment]}

    def _on_confirm(self, message: dict) -> dict:
        order_id = f"ride-{uuid.uuid4().hex[:8]}"
        order = {**message["order"], "id": order_id, "provider": self._provider()}
        self.orders[order_id] = order
        return {"order": self._ride(order, status="ACTIVE", state="RIDE_ASSIGNED")}

    def _on_status(self, message: dict) -> dict:
        order = self.orders[message["order_id"]]
        if self.mode == "cancel":
            return {"order": self._ride(order, status="CANCELLED", state="RIDE_CANCELLED")}
        return {"order": self._ride(order, status="ACTIVE", state=self.fulfilment_state)}

    def _on_cancel(self, message: dict) -> dict:
        order = self.orders[message["order_id"]]
        return {"order": self._ride(order, status="CANCELLED", state="RIDE_CANCELLED")}
