from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings."""

    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Storage settings
    STORAGE_BACKEND: str = "local"  # "local" or "drive"
    LOCAL_STORAGE_DIR: str = "./processed_assets"
    BASE_URL: str = "http://localhost:8000"

    # Google Cloud / Google Drive
    GOOGLE_SERVICE_ACCOUNT_JSON: Optional[str] = None
    GOOGLE_DRIVE_FOLDER_ID: Optional[str] = None

    # YouTube Data API v3
    YOUTUBE_API_KEY: Optional[str] = None

    # Constraints & Defaults
    HEADLINE_MAX_LENGTH: int = 30
    DESCRIPTION_MAX_LENGTH: int = 90
    IMAGE_MAX_SIZE_BYTES: int = 5 * 1024 * 1024  # 5.0 MB Google Ads max
    IMAGE_TARGET_COMPRESSION_BYTES: int = 3 * 1024 * 1024  # 3.0 MB target

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# Ensure local storage directory exists
Path(settings.LOCAL_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
