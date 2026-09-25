"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.deps import build_state
from .api.routes import router
from .config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    app.state.saathi = build_state(settings)
    yield


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
    return app


app = create_app()
