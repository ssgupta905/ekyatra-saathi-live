"""Where an open network's sellers answer: the Beckn `on_*` callbacks.

Unauthenticated in the sign-in sense; every callback is signed by its seller,
and `BecknProvider.handle_callback` verifies the signature against the
network registry's key before anything is believed.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .deps import ContainerDep

router = APIRouter(tags=["beckn"])


@router.post("/beckn/{network_id}/{action}")
async def callback(state: ContainerDep, network_id: str, action: str, request: Request):
    network = state.runner.network
    provider = network.providers.get(network_id) if network is not None else None
    handle = getattr(provider, "handle_callback", None)
    if handle is None:
        return JSONResponse(
            {"message": {"ack": {"status": "NACK"}}, "error": {"message": "unknown network"}},
            status_code=404,
        )
    reply = await handle(action, await request.body(), dict(request.headers))
    return JSONResponse(reply.body, status_code=reply.status)
