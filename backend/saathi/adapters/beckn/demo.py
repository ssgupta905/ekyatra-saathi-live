"""A Beckn network inside this process: the real buyer app, talking to a pretend seller.

For showing the whole ride — search, a seller's own quote, the family's Book,
a driver assigned — without an ONDC registration. Everything a real network
does is done for real here (every request and callback is signed and
verified); only the seller is pretend. `config.py` refuses it in production.
"""

from __future__ import annotations

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .client import BecknProvider
from .fake_bpp import FakeBpp
from .registry import StaticKeys, SubscriberRegistry
from .signing import public_key_to_b64

_BAP = "saathi.demo"
_BPP = "cabs.demo"
_BPP_URI = "https://cabs.demo.invalid/beckn"


class DemoNetwork(BecknProvider):
    """A `BecknProvider` whose only seller lives in the same process."""

    name = "beckn-demo"

    def __init__(self, *, provider_name: str = "Open-network cab (demo)") -> None:
        bap_key, bpp_key = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        registry = SubscriberRegistry(
            StaticKeys(
                {
                    (_BAP, "k1"): public_key_to_b64(bap_key.public_key()),
                    (_BPP, "k1"): public_key_to_b64(bpp_key.public_key()),
                }
            )
        )
        self.seller = FakeBpp(
            bpp_id=_BPP,
            bpp_uri=_BPP_URI,
            unique_key_id="k1",
            private_key=bpp_key,
            registry=registry,
            provider_name=provider_name,
        )
        super().__init__(
            bap_id=_BAP,
            bap_uri="https://saathi.demo.invalid/beckn",
            unique_key_id="k1",
            private_key=bap_key,
            registry=registry,
            gateway_url=_BPP_URI,
            city_code="std:022",
            timeout=5.0,
            search_window=0.3,
            client=httpx.AsyncClient(transport=self.seller.transport()),
        )
        self.seller.deliver = self.handle_callback

    @property
    def live(self) -> bool:
        return False

    async def close(self) -> None:
        await self.seller.aclose()
        await super().close()


__all__ = ["DemoNetwork"]
