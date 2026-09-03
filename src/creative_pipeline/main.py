from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from creative_pipeline.api.routes import (
    batch_router,
    health_router,
    image_router,
    text_router,
    video_router,
)
from creative_pipeline.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure processed assets directory exists on startup
    Path(settings.LOCAL_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Self-Healing Creative Pipeline API",
    description=(
        "Autonomous Google Ads Asset Validator, Auto-Corrector, Smart Cropper & Filter Microservice. "
        "Transforms raw, un-vetted headlines, descriptions, images, and videos into 100% policy-compliant assets."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Enable CORS for Next.js Portal / Webhook integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount local storage folder as static files
storage_path = Path(settings.LOCAL_STORAGE_DIR)
storage_path.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(storage_path)), name="assets")

# Register routes
app.include_router(health_router)
app.include_router(text_router)
app.include_router(image_router)
app.include_router(video_router)
app.include_router(batch_router)


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "Self-Healing Creative Pipeline API",
        "status": "online",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("creative_pipeline.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
