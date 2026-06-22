"""Public runtime config for the frontend."""
from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/config")
def config():
    """Tells the client which video backend to use."""
    return {
        "livekit_enabled": settings.livekit_enabled,
        "livekit_url": settings.livekit_url if settings.livekit_enabled else "",
    }
