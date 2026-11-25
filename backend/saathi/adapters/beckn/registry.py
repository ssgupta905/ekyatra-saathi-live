"""Whose key is this? A counterparty's signing public key, from the registry.

A Beckn message names its signer in the `keyId` (`subscriber_id|unique_key_id`)
and the registry says which public key that pair holds. Looking it up on every
callback would put the registry on the hot path of every ride, so answers are
cached for a while; a key that has been rotated stops verifying within one TTL.

The fetcher is injected. `RegistryLookup` speaks a registry's `/lookup` over
HTTP; `StaticKeys` is a dictionary, for tests and for a closed pilot where the
counterparties are known in advance. Neither result is cached when the lookup
fails — an outage must not be remembered as "this seller has no key".
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ...ports.network import NetworkUnavailable
from .signing import SignatureError, public_key_from_b64

#: (subscriber_id, unique_key_id) -> base64 public key, or None for "not registered".
Fetcher = Callable[[str, str], Awaitable[str | None]]


class UnknownSubscriber(SignatureError):
    """The registry answered, and has no such key. The message is not trusted."""


class StaticKeys:
    """A fixed table of keys. No network."""

    def __init__(self, keys: Mapping[tuple[str, str], str]) -> None:
        self._keys = dict(keys)

    def add(self, subscriber_id: str, unique_key_id: str, public_key_b64: str) -> None:
        self._keys[(subscriber_id, unique_key_id)] = public_key_b64

    async def __call__(self, subscriber_id: str, unique_key_id: str) -> str | None:
        return self._keys.get((subscriber_id, unique_key_id))


class RegistryLookup:
    """A registry's `/lookup` endpoint. Any failure is `NetworkUnavailable`."""

    def __init__(self, *, base_url: str, client: httpx.AsyncClient, timeout: float = 5.0):
        self._url = base_url.rstrip("/") + "/lookup"
        self._client = client
        self._timeout = timeout

    async def __call__(self, subscriber_id: str, unique_key_id: str) -> str | None:
        try:
            response = await self._client.post(
                self._url,
                json={"subscriber_id": subscriber_id, "ukId": unique_key_id},
                timeout=self._timeout,
            )
            response.raise_for_status()
            entries = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise NetworkUnavailable(f"registry lookup failed: {exc}") from exc
        if not isinstance(entries, list):
            raise NetworkUnavailable("registry lookup returned something other than a list")
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("subscriber_id") != subscriber_id:
                continue
            if entry.get("ukId", entry.get("unique_key_id")) != unique_key_id:
                continue
            key = entry.get("signing_public_key")
            if isinstance(key, str) and key:
                return key
        return None


class SubscriberRegistry:
    """Public keys by `(subscriber_id, unique_key_id)`, cached for `ttl` seconds."""

    def __init__(
        self,
        fetcher: Fetcher,
        *,
        ttl: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetcher
        self._ttl = ttl
        self._clock = clock
        self._cache: dict[tuple[str, str], tuple[Ed25519PublicKey, float]] = {}

    async def public_key(self, subscriber_id: str, unique_key_id: str) -> Ed25519PublicKey:
        """The key, or `UnknownSubscriber`. A registry outage is `NetworkUnavailable`."""
        pair = (subscriber_id, unique_key_id)
        cached = self._cache.get(pair)
        now = self._clock()
        if cached is not None and cached[1] > now:
            return cached[0]
        encoded = await self._fetch(subscriber_id, unique_key_id)
        if not encoded:
            self._cache.pop(pair, None)
            raise UnknownSubscriber(f"no key registered for {subscriber_id}|{unique_key_id}")
        key = public_key_from_b64(encoded)
        self._cache[pair] = (key, now + self._ttl)
        return key

    def forget(self, subscriber_id: str, unique_key_id: str) -> None:
        self._cache.pop((subscriber_id, unique_key_id), None)
