"""FastAPI application factory."""

import logging

from fastapi import FastAPI

from partner_reports import __version__
from partner_reports.config import Settings
from partner_reports.web.routes.health import router as health_router
from partner_reports.web.routes.portal import install_portal


def create_app(settings: Settings) -> FastAPI:
    """Build the application with explicitly validated settings."""

    # Uvicorn's default access log contains raw URL paths and query strings.
    logging.getLogger("uvicorn.access").disabled = True
    app = FastAPI(
        title="Plataforma de Relatórios de Parceiros",
        version=__version__,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.include_router(health_router)
    install_portal(app)
    return app
