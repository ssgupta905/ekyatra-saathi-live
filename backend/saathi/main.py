"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.board import router as board_router
from .api.family import router as family_router
from .api.live import router as live_router
from .api.records import router as records_router
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
    app.include_router(records_router, prefix="/api")
    app.include_router(family_router, prefix="/api")
    return app


app = create_app()
