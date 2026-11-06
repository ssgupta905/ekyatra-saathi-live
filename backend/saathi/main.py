"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.admin import router as admin_router
from .api.auth import router as auth_router
from .api.board import router as board_router
from .api.consent import router as consent_router
from .api.demo import router as demo_router
from .api.directory import router as directory_router
from .api.family import router as family_router
from .api.guide import router as guide_router
from .api.live import router as live_router
from .api.onboarding import router as onboarding_router
from .api.partner import router as partner_router
from .api.readiness import router as readiness_router
from .api.records import router as records_router
from .api.registry import router as registry_router
from .api.reports import router as reports_router
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
    app.include_router(auth_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.include_router(live_router, prefix="/api")
    app.include_router(board_router, prefix="/api")
    app.include_router(records_router, prefix="/api")
    app.include_router(readiness_router, prefix="/api")
    app.include_router(consent_router, prefix="/api")
    app.include_router(registry_router, prefix="/api")
    app.include_router(directory_router, prefix="/api")
    app.include_router(demo_router, prefix="/api")
    app.include_router(onboarding_router, prefix="/api")
    app.include_router(reports_router, prefix="/api")
    app.include_router(family_router, prefix="/api")
    app.include_router(guide_router, prefix="/api")
    app.include_router(partner_router, prefix="/api")
    return app


app = create_app()
