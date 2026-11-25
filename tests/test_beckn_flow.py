"""The Beckn buyer app against an in-process seller: the whole ride, and its failures.

No sockets: the seller is an `httpx.MockTransport`, and its callbacks are
handed straight to `BecknProvider.handle_callback`.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from saathi.adapters.beckn import BecknProvider, NoNetwork, StaticKeys, SubscriberRegistry
from saathi.adapters.beckn.fake_bpp import FakeBpp
from saathi.adapters.beckn.signing import public_key_to_b64, sign_body
from saathi.ports.network import (
    Fulfilment,
    GeoPoint,
    NetworkProvider,
    NetworkUnavailable,
    OrderState,
    QuoteChanged,
    SearchIntent,
)

BAP = "bap.saathi.test"
BPP = "bpp.fakecabs.test"
BPP_URI = "https://bpp.fakecabs.test/beckn"
INTENT = SearchIntent(
    pickup=GeoPoint(12.9352, 77.6245), drop=GeoPoint(12.9416, 77.5993), vehicle_category="CAB"
)
FAMILY = Fulfilment(customer_name="Lakshmi", customer_phone="9000000000")


def _world(**bpp_options):
    bap_key, bpp_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    keys = StaticKeys(
        {
            (BAP, "bap-k1"): public_key_to_b64(bap_key.public_key()),
            (BPP, "bpp-k1"): public_key_to_b64(bpp_key.public_key()),
        }
    )
    registry = SubscriberRegistry(keys)
    bpp = FakeBpp(
        bpp_id=BPP,
        bpp_uri=BPP_URI,
        unique_key_id="bpp-k1",
        private_key=bpp_key,
        registry=registry,
        **bpp_options,
    )
    provider = BecknProvider(
        bap_id=BAP,
        bap_uri="https://saathi.test/beckn",
        unique_key_id="bap-k1",
        private_key=bap_key,
        registry=registry,
        gateway_url=BPP_URI,
        city_code="std:080",
        timeout=0.3,
        search_window=0.05,
        client=httpx.AsyncClient(transport=bpp.transport()),
    )
    bpp.deliver = provider.handle_callback
    return provider, bpp, bpp_key


@pytest.fixture
async def world():
    made = []

    def make(**options):
        made.append(_world(**options))
        return made[-1]

    yield make
    for provider, bpp, _ in made:
        await bpp.aclose()
        await provider.close()


def test_both_adapters_satisfy_the_port():
    def accepts(p: NetworkProvider) -> str:
        return p.name

    assert accepts(NoNetwork()) == "none"
    assert BecknProvider.name == "beckn"


async def test_search_select_init_confirm_status(world):
    provider, bpp, _ = world()

    offers = await provider.search(INTENT)
    assert [o.vehicle_category for o in offers] == ["CAB"]
    offer = offers[0]
    assert offer.network == BPP and offer.estimated_paise == 14550

    quote = await provider.quote(offer.id)
    assert quote.amount_paise == 14550 and quote.currency == "INR"
    assert [(line.title, line.amount_paise) for line in quote.breakup] == [
        ("BASE_FARE", 5000),
        ("DISTANCE_FARE", 9550),
    ]

    order = await provider.confirm(quote.id, FAMILY)
    assert order.state is OrderState.CONFIRMED
    assert order.quote_id == quote.id and order.amount_paise == 14550
    assert order.driver_name == "Ramesh K" and order.start_otp == "4821"
    assert bpp.actions() == ["search", "select", "init", "confirm"]

    init_payload = dict(bpp.received)["init"]
    assert init_payload["context"]["domain"] == "ONDC:TRV10"
    assert init_payload["context"]["bpp_id"] == BPP
    assert init_payload["message"]["order"]["billing"]["phone"] == FAMILY.customer_phone

    status = await provider.status(order.id)
    assert status.id == order.id and status.state is OrderState.CONFIRMED

    cancelled = await provider.cancel(order.id, "Appointment moved")
    assert cancelled.state is OrderState.CANCELLED
    assert dict(bpp.received)["cancel"]["message"]["descriptor"]["name"] == "Appointment moved"


async def test_a_search_does_not_carry_the_family(world):
    provider, bpp, _ = world()
    await provider.search(INTENT)
    sent = json.dumps(bpp.received[0][1])
    assert FAMILY.customer_phone not in sent and FAMILY.customer_name not in sent


async def test_quoting_books_nothing(world):
    provider, bpp, _ = world()
    offers = await provider.search(INTENT)
    await provider.quote(offers[0].id)
    assert "init" not in bpp.actions() and "confirm" not in bpp.actions()
    assert bpp.orders == {}


async def test_confirming_twice_books_one_ride(world):
    provider, bpp, _ = world()
    quote = await provider.quote((await provider.search(INTENT))[0].id)
    first = await provider.confirm(quote.id, FAMILY)
    second = await provider.confirm(quote.id, FAMILY)
    assert first == second
    assert bpp.actions().count("confirm") == 1


async def test_no_callback_is_unavailable(world):
    provider, _, _ = world(mode="never")
    with pytest.raises(NetworkUnavailable, match="no seller answered"):
        await provider.search(INTENT)


async def test_a_seller_that_goes_quiet_after_the_search_is_unavailable(world):
    provider, _, _ = world(silent_on={"select"})
    offers = await provider.search(INTENT)
    with pytest.raises(NetworkUnavailable, match="no on_select"):
        await provider.quote(offers[0].id)


async def test_a_late_answer_within_the_timeout_still_counts(world):
    provider, _, _ = world(mode="late", delay=0.01)
    offers = await provider.search(INTENT)
    assert (await provider.quote(offers[0].id)).amount_paise == 14550


async def test_an_answer_after_the_timeout_is_unavailable_and_then_ignored(world):
    provider, bpp, _ = world()
    offers = await provider.search(INTENT)
    bpp.mode, bpp.delay = "late", 0.5
    with pytest.raises(NetworkUnavailable):
        await provider.quote(offers[0].id)
    await asyncio.sleep(0.3)
    assert provider.unsolicited and provider.unsolicited[-1]["context"]["action"] == "on_select"


async def test_unknown_fulfilment_state_is_unknown(world):
    provider, _, _ = world(fulfilment_state="RIDE_TELEPORTED")
    quote = await provider.quote((await provider.search(INTENT))[0].id)
    order = await provider.confirm(quote.id, FAMILY)
    status = await provider.status(order.id)
    assert status.state is OrderState.UNKNOWN
    assert status.vendor_state == "RIDE_TELEPORTED"


async def test_a_seller_cancellation_reads_as_cancelled(world):
    provider, _, _ = world(mode="cancel")
    quote = await provider.quote((await provider.search(INTENT))[0].id)
    order = await provider.confirm(quote.id, FAMILY)
    assert (await provider.status(order.id)).state is OrderState.CANCELLED


async def test_a_changed_final_price_books_nothing(world):
    provider, bpp, _ = world(init_fare="190.00")
    quote = await provider.quote((await provider.search(INTENT))[0].id)
    with pytest.raises(QuoteChanged) as raised:
        await provider.confirm(quote.id, FAMILY)
    assert (raised.value.quoted_paise, raised.value.offered_paise) == (14550, 19000)
    assert "confirm" not in bpp.actions()


async def test_an_unreachable_seller_is_unavailable():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    key = Ed25519PrivateKey.generate()
    provider = BecknProvider(
        bap_id=BAP,
        bap_uri="https://saathi.test/beckn",
        unique_key_id="bap-k1",
        private_key=key,
        registry=SubscriberRegistry(StaticKeys({})),
        gateway_url=BPP_URI,
        city_code="std:080",
        timeout=0.1,
        search_window=0.01,
        client=httpx.AsyncClient(transport=httpx.MockTransport(refuse)),
    )
    with pytest.raises(NetworkUnavailable, match="failed"):
        await provider.search(INTENT)
    await provider.close()


async def test_a_nack_is_unavailable():
    def nack(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"ack": {"status": "NACK"}}})

    provider = BecknProvider(
        bap_id=BAP,
        bap_uri="https://saathi.test/beckn",
        unique_key_id="bap-k1",
        private_key=Ed25519PrivateKey.generate(),
        registry=SubscriberRegistry(StaticKeys({})),
        gateway_url=BPP_URI,
        city_code="std:080",
        timeout=0.1,
        search_window=0.01,
        client=httpx.AsyncClient(transport=httpx.MockTransport(nack)),
    )
    with pytest.raises(NetworkUnavailable, match="not acknowledged"):
        await provider.search(INTENT)
    await provider.close()


async def test_callbacks_that_are_not_provably_from_the_seller_are_refused(world):
    provider, _, bpp_key = world()
    body = json.dumps(
        {"context": {"action": "on_search", "bap_id": BAP, "bpp_id": BPP, "message_id": "m"},
         "message": {}}
    ).encode()

    def signed(key, subscriber=BPP, key_id="bpp-k1", payload=body):
        return sign_body(payload, private_key=key, subscriber_id=subscriber,
                         unique_key_id=key_id)

    ok = await provider.handle_callback("on_search", body, {"authorization": signed(bpp_key)})
    assert ok.status == 200 and ok.acked

    unsigned = await provider.handle_callback("on_search", body, {})
    assert unsigned.status == 401

    forged = await provider.handle_callback(
        "on_search", body, {"Authorization": signed(Ed25519PrivateKey.generate())}
    )
    assert forged.status == 401

    stranger = await provider.handle_callback(
        "on_search", body, {"Authorization": signed(bpp_key, subscriber="nobody")}
    )
    assert stranger.status == 401

    tampered = body.replace(b'"m"', b'"n"')
    altered = await provider.handle_callback(
        "on_search", tampered, {"Authorization": signed(bpp_key)}
    )
    assert altered.status == 401


async def test_no_network_says_so():
    with pytest.raises(NetworkUnavailable):
        await NoNetwork().search(INTENT)
    assert NoNetwork().live is False
