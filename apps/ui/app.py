"""UNS UI Application.

This module provides a FastAPI application for the UNS Dashboard API.
It provides JSON API endpoints for the React frontend to consume,
serving data about notification delivery timelines, policies,
invariants, and audit events.

Per ui-scope.md: This is a read-only "flight instruments" dashboard.
No mutation operations are permitted in v1.

Note: This module provides JSON API responses. The React frontend
(built separately) handles all HTML rendering.

Usage:
    # Run standalone API server
    uvicorn apps.ui.app:app --reload --port 8001

    # Or mount into main app
    from apps.ui.app import create_ui_app
    main_app.mount("/ui", create_ui_app())
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from apps.ui.src.pages import deliveries_router

# Paths
_app_dir = Path(__file__).parent
_static_dir = _app_dir / "static"


def create_ui_app() -> FastAPI:
    """Create and configure the UI FastAPI application.

    Returns:
        Configured FastAPI app with UI routes and static files
    """
    app = FastAPI(
        title="UNS Dashboard",
        description="Read-only dashboard for the Unified Notification Service",
        version="0.1.0",
        docs_url=None,  # Disable Swagger UI for the dashboard
        redoc_url=None,  # Disable ReDoc
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

    # Include page routers
    app.include_router(deliveries_router)

    @app.get("/")
    async def index():
        """Redirect to deliveries page."""
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/pages/deliveries/")

    return app


# Default app instance for uvicorn
app = create_ui_app()
