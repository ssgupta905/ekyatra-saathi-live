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


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    # The world starts a few days back so reports land while someone is
    # watching, rather than having all landed before the demo begins.
    container = build_container(settings, today=default_start(settings.live_start_offset_days))
    app.state.container = container
    await start_runner(container)
    try:
        yield
    finally:
        await stop_runner(container)
