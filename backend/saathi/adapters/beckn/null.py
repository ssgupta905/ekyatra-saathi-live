"""No network configured. Every request says so, and nothing is guessed."""

from __future__ import annotations

from ...ports.network import Fulfilment, NetworkUnavailable, Offer, Order, Quote, SearchIntent


class NoNetwork:
    """`NetworkProvider` for a deployment with no mobility network.

    Raises rather than returning empty results: "no rides found" is a claim
    about the city, and with no network we have not asked the city anything.
    """

    name = "none"

    @property
    def live(self) -> bool:
        return False

    async def search(self, intent: SearchIntent) -> tuple[Offer, ...]:
        raise NetworkUnavailable("no mobility network is configured")

    async def quote(self, offer_id: str) -> Quote:
        raise NetworkUnavailable("no mobility network is configured")

    async def confirm(self, quote_id: str, fulfilment: Fulfilment) -> Order:
        raise NetworkUnavailable("no mobility network is configured")

    async def status(self, order_id: str) -> Order:
        raise NetworkUnavailable("no mobility network is configured")

    async def cancel(self, order_id: str, reason: str) -> Order:
        raise NetworkUnavailable("no mobility network is configured")

    async def close(self) -> None:
        return None
