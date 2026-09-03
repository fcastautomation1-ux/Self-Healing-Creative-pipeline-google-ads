from .batch import router as batch_router
from .health import router as health_router
from .image import router as image_router
from .text import router as text_router
from .video import router as video_router

__all__ = [
    "health_router",
    "text_router",
    "image_router",
    "video_router",
    "batch_router",
]
