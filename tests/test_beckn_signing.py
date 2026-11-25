"""Beckn signatures: they verify, and nothing that should fail does not."""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from saathi.adapters.beckn.registry import StaticKeys, SubscriberRegistry, UnknownSubscriber
from saathi.adapters.beckn.signing import (
    SignatureError,
    load_private_key,
    parse_header,
    public_key_from_b64,
    public_key_to_b64,
    sign_body,
    verify_body,
)

BODY = b'{"context":{"action":"search"},"message":{}}'
T0 = 1_760_000_000


def _sign(key: Ed25519PrivateKey, body: bytes = BODY, at: float = T0, ttl: int = 300) -> str:
    return sign_body(
        body,
        private_key=key,
        subscriber_id="bap.example",
        unique_key_id="k1",
        ttl=ttl,
        now=lambda: at,
    )


def test_round_trip():
    key = Ed25519PrivateKey.generate()
    header = _sign(key)
    signer = verify_body(BODY, header, public_key=key.public_key(), now=lambda: T0 + 10)
    assert (signer.subscriber_id, signer.unique_key_id) == ("bap.example", "k1")
    assert signer.expires == T0 + 300


def test_header_has_the_beckn_shape():
    header = _sign(Ed25519PrivateKey.generate())
    assert header.startswith('Signature keyId="bap.example|k1|ed25519",algorithm="ed25519"')
    assert 'headers="(created) (expires) digest"' in header
    parsed = parse_header(header)
    assert parsed.created == T0 and parsed.expires == T0 + 300


def test_unquoted_created_and_expires_also_parse():
    header = _sign(Ed25519PrivateKey.generate()).replace(f'"{T0}"', str(T0))
    assert parse_header(header).created == T0


def test_tampered_body_fails():
    key = Ed25519PrivateKey.generate()
    header = _sign(key)
    with pytest.raises(SignatureError, match="does not verify"):
        verify_body(BODY.replace(b"search", b"select"), header, public_key=key.public_key(),
                    now=lambda: T0)


def test_expired_fails():
    key = Ed25519PrivateKey.generate()
    header = _sign(key, ttl=60)
    with pytest.raises(SignatureError, match="expired"):
        verify_body(BODY, header, public_key=key.public_key(), now=lambda: T0 + 61)


def test_created_in_the_future_fails():
    key = Ed25519PrivateKey.generate()
    header = _sign(key, at=T0 + 120)
    with pytest.raises(SignatureError, match="future"):
        verify_body(BODY, header, public_key=key.public_key(), now=lambda: T0)


def test_wrong_key_fails():
    header = _sign(Ed25519PrivateKey.generate())
    other = Ed25519PrivateKey.generate().public_key()
    with pytest.raises(SignatureError, match="does not verify"):
        verify_body(BODY, header, public_key=other, now=lambda: T0)


def test_malformed_header_fails():
    with pytest.raises(SignatureError):
        parse_header('Signature keyId="only-one-part",signature="x"')
    with pytest.raises(SignatureError):
        parse_header("")


def test_public_key_round_trips_through_the_registry_form():
    key = Ed25519PrivateKey.generate().public_key()
    encoded = public_key_to_b64(key)
    assert len(base64.b64decode(encoded)) == 32
    assert public_key_to_b64(public_key_from_b64(encoded)) == encoded


@pytest.mark.parametrize("form", ["pem", "seed", "nacl"])
def test_private_keys_load_from_files(tmp_path, form):
    key = Ed25519PrivateKey.generate()
    seed = key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    path = tmp_path / "signing.key"
    if form == "pem":
        path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    elif form == "seed":
        path.write_text(base64.b64encode(seed).decode())
    else:
        path.write_text(base64.b64encode(seed + public).decode())

    loaded = load_private_key(path)
    header = _sign(loaded)
    verify_body(BODY, header, public_key=key.public_key(), now=lambda: T0)


async def test_registry_caches_for_its_ttl_and_not_failures():
    key = Ed25519PrivateKey.generate().public_key()
    calls: list[tuple[str, str]] = []
    table = StaticKeys({("bpp.example", "k1"): public_key_to_b64(key)})

    async def fetch(subscriber_id: str, unique_key_id: str) -> str | None:
        calls.append((subscriber_id, unique_key_id))
        return await table(subscriber_id, unique_key_id)

    clock = [0.0]
    registry = SubscriberRegistry(fetch, ttl=60, clock=lambda: clock[0])
    await registry.public_key("bpp.example", "k1")
    await registry.public_key("bpp.example", "k1")
    assert len(calls) == 1
    clock[0] = 61
    await registry.public_key("bpp.example", "k1")
    assert len(calls) == 2

    with pytest.raises(UnknownSubscriber):
        await registry.public_key("stranger", "k1")
    with pytest.raises(UnknownSubscriber):
        await registry.public_key("stranger", "k1")
    assert calls.count(("stranger", "k1")) == 2
