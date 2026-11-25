"""Application lifecycle: build the container, start background work, stop it."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..config import get_settings
from ..live.world import default_start
from .container import Container, build_container


async def start_runner(container: Container) -> None:
    """Autostart is opt-in."""
    container.bus.bind_loop(asyncio.get_running_loop())
    await container.runner.start()
    if container.settings.live_autostart:
        await container.runner.play()


async def stop_runner(container: Container) -> None:
    with contextlib.suppress(Exception):
        await container.runner.stop()
    # The hospital connectors hold open HTTP clients; let them go cleanly.
    if container.hospitals is not None:
        with contextlib.suppress(Exception):
            container.hospitals.close()
    if container.runner.network is not None:
        with contextlib.suppress(Exception):
            await container.runner.network.close()
    if container.places is not None:
        with contextlib.suppress(Exception):
            await container.places.close()
    if container.routes is not None:
        with contextlib.suppress(Exception):
            await container.routes.close()
    if container.runner.payments is not None:
        with contextlib.suppress(Exception):
            container.runner.payments.close()


async def _warm_places(container: Container) -> None:
    """Ask for what is around each hospital's door ahead of time, if the finder can remember."""
    finder, registry = container.places, container.registry
    if finder is None or registry is None or not hasattr(finder, "warm"):
        return
    points = [(h.latitude, h.longitude) for h in registry.hospitals() if h.latitude is not None]
    with contextlib.suppress(Exception):
        await finder.warm(points)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    # The world starts a few days back so reports land while someone is
    # watching, rather than having all landed before the demo begins.
    container = build_container(settings, today=default_start(settings.live_start_offset_days))
    app.state.container = container
    await start_runner(container)
    warming = asyncio.create_task(_warm_places(container))
    try:
        yield
    finally:
        warming.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await warming
        await stop_runner(container)
