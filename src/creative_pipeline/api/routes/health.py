from fastapi import APIRouter
from creative_pipeline.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health")
@router.get("/v1/health")
async def health_check():
    """Health check endpoint indicating service status."""
    return {
        "status": "healthy",
        "service": "Self-Healing Creative Pipeline API",
        "version": "0.1.0",
        "environment": settings.ENVIRONMENT,
        "storage_backend": settings.STORAGE_BACKEND,
        "youtube_api_configured": bool(settings.YOUTUBE_API_KEY),
    }
