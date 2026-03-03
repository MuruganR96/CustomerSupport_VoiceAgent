"""FastAPI application entry point."""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .api import sessions, health

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Customer Support Voice Agent with LangGraph + LiveKit",
    )

    # CORS
    origins = [o.strip() for o in settings.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(health.router)
    app.include_router(sessions.router)

    @app.on_event("startup")
    async def startup():
        logger.info(f"Starting {settings.app_name}")
        logger.info(f"LiveKit URL: {settings.livekit_url}")

    @app.on_event("shutdown")
    async def shutdown():
        logger.info("Shutting down application")

    return app


app = create_app()
