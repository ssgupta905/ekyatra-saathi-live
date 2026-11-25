"""Where a vendor's payment gateway says a family has paid.

No sign-in, because the caller is a gateway, not a person; instead every
delivery must carry the gateway's signature over the exact bytes received,
checked against that vendor's webhook secret. Anything that does not verify is
refused and records nothing.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .deps import ContainerDep

router = APIRouter(tags=["payments"])


@router.post("/webhooks/payments/{account_id}")
async def payment_webhook(state: ContainerDep, account_id: str, request: Request) -> dict:
    payments = state.runner.payments
    if payments is None:
        raise HTTPException(404, "no such account")
    raw = await request.body()
    try:
        outcome = payments.webhook(account_id, raw, dict(request.headers))
    except PermissionError as exc:
        raise HTTPException(401, "signature did not verify") from exc
    return {"ok": True, "outcome": outcome}
