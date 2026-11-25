"""Small helpers every payments adapter needs."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

import httpx

from ...ports.payments import PaymentUnavailable


def header(headers: Mapping[str, str], name: str) -> str | None:
    """A header by name, ignoring case. Frameworks disagree on casing."""
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def hmac_sha256(secret: str, message: bytes) -> bytes:
    return hmac.new(secret.encode(), message, hashlib.sha256).digest()


def same(a: str, b: str) -> bool:
    """Constant-time string comparison, so timing does not leak a signature."""
    return hmac.compare_digest(a.encode(), b.encode())


def body_digest(raw_body: bytes) -> str:
    """A stable event id for a gateway that did not send one."""
    return "sha256:" + hashlib.sha256(raw_body).hexdigest()


def paise_from_rupees(value: object) -> int:
    """A gateway's rupee amount, as paise, without passing through a float.

    `str()` first because `Decimal(0.1)` is the float's binary expansion, not
    the 0.1 the gateway wrote.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PaymentUnavailable(f"amount {value!r} is not a number")
    try:
        paise = Decimal(str(value)) * 100
    except InvalidOperation as exc:
        raise PaymentUnavailable(f"amount {value!r} is not a number") from exc
    if paise != paise.to_integral_value():
        raise PaymentUnavailable(f"amount {value!r} has fractional paise")
    return int(paise)


def rupees_for_wire(amount_paise: int) -> float:
    """Paise as the rupee number a JSON body needs. Exact to two places.

    Only ever called while building a request body: the shortest float repr of
    n/100 is the two-decimal string, so the gateway reads what we meant.
    """
    return float(Decimal(amount_paise) / 100)


def send(
    client: httpx.Client,
    provider: str,
    method: str,
    url: str,
    **kwargs: object,
) -> dict:
    """One request, with every transport, status and JSON failure as PaymentUnavailable."""
    try:
        response = client.request(method, url, **kwargs)  # type: ignore[arg-type]
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # The gateway's reason is in the body; without it every failure looks
        # the same. Truncated, and the request (which carries auth) is not.
        detail = exc.response.text[:400].strip()
        raise PaymentUnavailable(
            f"{provider} {method} -> {exc.response.status_code}: {detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise PaymentUnavailable(f"{provider} {method}: {type(exc).__name__}") from exc
    try:
        body = response.json()
    except ValueError as exc:
        raise PaymentUnavailable(f"{provider} {method}: body was not JSON") from exc
    if not isinstance(body, dict):
        raise PaymentUnavailable(f"{provider} {method}: body was not an object")
    return body
