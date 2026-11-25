"""Beckn message signing: ed25519 over a BLAKE2b-512 digest of the exact body.

Every request and every callback on a Beckn network carries an
`Authorization` header that proves who sent it and that the body was not
altered on the way:

    Signature keyId="<subscriber_id>|<unique_key_id>|ed25519",
              algorithm="ed25519",created="<unix>",expires="<unix>",
              headers="(created) (expires) digest",signature="<base64>"

The signed string is three lines — `(created)`, `(expires)` and `digest` — and
the digest is BLAKE2b-512 of the raw body bytes, base64 encoded. The raw bytes
matter: re-serialising a parsed JSON body changes whitespace and key order and
breaks every signature, so callers verify what came off the wire.

Keys are objects or file paths. Nothing here reads an environment variable, and
no key is ever written into code or a test.
"""

from __future__ import annotations

import base64
import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

ALGORITHM = "ed25519"
SIGNED_HEADERS = "(created) (expires) digest"
#: How far in the future a `created` may be before we call it forged. Clocks
#: drift; seconds of drift are normal, minutes are not.
DEFAULT_SKEW = 5


class SignatureError(ValueError):
    """A header that is missing, malformed, expired, or does not verify."""


@dataclass(frozen=True)
class SignedBy:
    """Who a verified header says signed the message."""

    subscriber_id: str
    unique_key_id: str
    created: int
    expires: int


def body_digest(body: bytes) -> str:
    """`BLAKE-512=<base64>` without the prefix: the base64 BLAKE2b-512 of `body`."""
    return base64.b64encode(hashlib.blake2b(body, digest_size=64).digest()).decode()


def signing_string(body: bytes, created: int, expires: int) -> str:
    return (
        f"(created): {created}\n(expires): {expires}\ndigest: BLAKE-512={body_digest(body)}"
    )


def sign_body(
    body: bytes,
    *,
    private_key: Ed25519PrivateKey,
    subscriber_id: str,
    unique_key_id: str,
    ttl: int = 300,
    now: Callable[[], float] = time.time,
) -> str:
    """Build the full `Authorization` header value for `body`."""
    created = int(now())
    expires = created + ttl
    signature = base64.b64encode(
        private_key.sign(signing_string(body, created, expires).encode())
    ).decode()
    return (
        f'Signature keyId="{subscriber_id}|{unique_key_id}|{ALGORITHM}",'
        f'algorithm="{ALGORITHM}",created="{created}",expires="{expires}",'
        f'headers="{SIGNED_HEADERS}",signature="{signature}"'
    )


_PARAM = re.compile(r'(\w+)=(?:"([^"]*)"|([^,\s]*))')


@dataclass(frozen=True)
class ParsedHeader:
    subscriber_id: str
    unique_key_id: str
    algorithm: str
    created: int
    expires: int
    headers: str
    signature: bytes


def parse_header(value: str) -> ParsedHeader:
    """Split an `Authorization: Signature ...` value into its parts. No verifying."""
    if not value:
        raise SignatureError("no Authorization header")
    text = value.strip()
    if text.lower().startswith("signature "):
        text = text[len("signature ") :]
    params = {m.group(1): m.group(2) if m.group(2) is not None else m.group(3)
              for m in _PARAM.finditer(text)}
    try:
        subscriber_id, unique_key_id, key_algorithm = params["keyId"].split("|")
        created = int(params["created"])
        expires = int(params["expires"])
        signature = base64.b64decode(params["signature"], validate=True)
    except (KeyError, ValueError) as exc:
        raise SignatureError(f"malformed Authorization header: {exc}") from exc
    algorithm = params.get("algorithm", key_algorithm)
    if algorithm != ALGORITHM or key_algorithm != ALGORITHM:
        raise SignatureError(f"unsupported algorithm {algorithm!r}")
    return ParsedHeader(
        subscriber_id=subscriber_id,
        unique_key_id=unique_key_id,
        algorithm=algorithm,
        created=created,
        expires=expires,
        headers=params.get("headers", SIGNED_HEADERS),
        signature=signature,
    )


def verify_body(
    body: bytes,
    header: str | ParsedHeader,
    *,
    public_key: Ed25519PublicKey,
    now: Callable[[], float] = time.time,
    skew: int = DEFAULT_SKEW,
) -> SignedBy:
    """Check `header` signs exactly `body` with `public_key`, and is in date."""
    parsed = parse_header(header) if isinstance(header, str) else header
    if parsed.headers != SIGNED_HEADERS:
        raise SignatureError(f"unexpected signed headers {parsed.headers!r}")
    moment = int(now())
    if parsed.created > moment + skew:
        raise SignatureError("signature created in the future")
    if parsed.expires <= moment:
        raise SignatureError("signature expired")
    if parsed.expires <= parsed.created:
        raise SignatureError("signature expires before it was created")
    try:
        public_key.verify(
            parsed.signature,
            signing_string(body, parsed.created, parsed.expires).encode(),
        )
    except InvalidSignature as exc:
        raise SignatureError("signature does not verify") from exc
    return SignedBy(
        subscriber_id=parsed.subscriber_id,
        unique_key_id=parsed.unique_key_id,
        created=parsed.created,
        expires=parsed.expires,
    )


# --- keys ------------------------------------------------------------------


def public_key_to_b64(key: Ed25519PublicKey) -> str:
    """The raw 32-byte key, base64 — the form a Beckn registry publishes."""
    raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def public_key_from_b64(value: str) -> Ed25519PublicKey:
    """Read a registry's `signing_public_key`: raw 32 bytes, or DER SPKI, base64."""
    try:
        raw = base64.b64decode(value.strip(), validate=True)
        if len(raw) == 32:
            return Ed25519PublicKey.from_public_bytes(raw)
        key = serialization.load_der_public_key(raw)
    except ValueError as exc:
        raise SignatureError(f"unreadable public key: {exc}") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise SignatureError("public key is not ed25519")
    return key


def load_private_key(path: str | Path) -> Ed25519PrivateKey:
    """Read a signing key from a file: PKCS#8 PEM, or base64 of the raw key.

    Beckn tooling hands out the raw form two ways — the 32-byte seed, or the
    64-byte seed-plus-public-key that NaCl uses — and both are accepted.
    """
    data = Path(path).read_bytes().strip()
    if data.startswith(b"-----BEGIN"):
        key = serialization.load_pem_private_key(data, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise SignatureError(f"{path} is not an ed25519 key")
        return key
    try:
        raw = base64.b64decode(data, validate=True)
    except ValueError as exc:
        raise SignatureError(f"{path} is neither PEM nor base64") from exc
    if len(raw) not in (32, 64):
        raise SignatureError(f"{path} holds {len(raw)} bytes, not an ed25519 key")
    return Ed25519PrivateKey.from_private_bytes(raw[:32])
