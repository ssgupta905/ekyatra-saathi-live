"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.board import router as board_router
from .api.deps import build_state
from .api.family import router as family_router
from .api.live import router as live_router
from .api.live import start_runner, stop_runner
from .api.routes import router
from .config import get_settings
from .live.world import default_start


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    # The world starts a few days back so reports land while someone is
    # watching, rather than having all landed before the demo begins.
    state = build_state(settings, today=default_start(settings.live_start_offset_days))
    app.state.saathi = state
    await start_runner(state)
    try:
        yield
    finally:
        await stop_runner(state)


def create_app() -> FastAPI:
    app = FastAPI(
        title="EKYATRA Saathi",
        version="0.1.0",
        summary="Readiness-driven visit planning for families travelling for cancer care.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    app.include_router(live_router, prefix="/api")
    app.include_router(board_router, prefix="/api")
    app.include_router(family_router, prefix="/api")
    return app


app = create_app()
