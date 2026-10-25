"""FastAPI application entry point."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.board import router as board_router
from .api.family import router as family_router
from .api.live import router as live_router
from .api.routes import router
from .bootstrap.lifespan import lifespan
from .config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="EKYATRA Saathi",
        version="0.1.0",
        summary="Readiness-driven visit planning for families travelling for cancer care.",
        lifespan=lifespan,
    )
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    app.include_router(live_router, prefix="/api")
    app.include_router(board_router, prefix="/api")
    app.include_router(family_router, prefix="/api")
    _serve_console(app, settings.console_dist)
    return app


def _serve_console(app: FastAPI, dist: str) -> None:
    """Serve the built console from this same service, when one is present.

    Deployed, the three apps and the API are one origin. That is not a
    convenience: the recording stage loads the family and hospital apps into
    iframes by origin, and splitting them across two hosts would put a
    cross-origin boundary through the middle of the demo for nothing.

    Mounted last, so every `/api` route is matched before this catch-all. In
    development `console_dist` is empty and Vite serves the apps instead.
    """
    if not dist:
        return
    root = Path(dist)
    if not root.is_dir():
        logging.getLogger(__name__).warning("console_dist %s does not exist", root)
        return
    app.mount("/", StaticFiles(directory=root, html=True), name="console")


app = create_app()
