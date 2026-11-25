"""The `context` block every Beckn message opens with.

It says which network conversation a message belongs to (`transaction_id`),
which request it answers (`message_id`), who is talking to whom, and how long
the sender will wait. Callbacks are matched to requests on `message_id` alone,
so it is generated fresh for every request and never reused.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

DOMAIN = "ONDC:TRV10"
CORE_VERSION = "2.0.1"


def new_id() -> str:
    return str(uuid.uuid4())


def timestamp(moment: datetime | None = None) -> str:
    """RFC 3339 with milliseconds and a `Z`, which is what ONDC validators expect."""
    moment = (moment or datetime.now(UTC)).astimezone(UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def build_context(
    *,
    action: str,
    bap_id: str,
    bap_uri: str,
    transaction_id: str,
    city_code: str,
    message_id: str | None = None,
    bpp_id: str = "",
    bpp_uri: str = "",
    ttl: str = "PT30S",
    country_code: str = "IND",
    domain: str = DOMAIN,
    version: str = CORE_VERSION,
    moment: datetime | None = None,
) -> dict:
    """One request's context. `bpp_*` are omitted on a broadcast search."""
    context = {
        "domain": domain,
        "action": action,
        "version": version,
        "bap_id": bap_id,
        "bap_uri": bap_uri,
        "transaction_id": transaction_id,
        "message_id": message_id or new_id(),
        "timestamp": timestamp(moment),
        "ttl": ttl,
        "location": {
            "country": {"code": country_code},
            "city": {"code": city_code},
        },
    }
    if bpp_id:
        context["bpp_id"] = bpp_id
    if bpp_uri:
        context["bpp_uri"] = bpp_uri
    return context
