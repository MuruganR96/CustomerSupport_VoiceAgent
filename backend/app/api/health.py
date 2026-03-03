"""Health check endpoint."""

from fastapi import APIRouter
from ..models.schemas import HealthResponse
from ..core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check for all services."""
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        services={
            "livekit": settings.livekit_url,
            "stt": settings.stt_service_url,
            "tts": settings.tts_service_url,
        },
    )
