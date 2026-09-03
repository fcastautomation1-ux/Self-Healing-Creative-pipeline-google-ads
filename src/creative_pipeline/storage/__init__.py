from typing import Optional

from creative_pipeline.config import settings
from creative_pipeline.storage.base import BaseStorage
from creative_pipeline.storage.local import LocalStorage
from creative_pipeline.storage.drive import GoogleDriveStorage

__all__ = ["BaseStorage", "LocalStorage", "GoogleDriveStorage", "get_storage"]


def get_storage(backend: Optional[str] = None) -> BaseStorage:
    """Factory function to get storage provider instance."""
    mode = backend or settings.STORAGE_BACKEND
    if mode == "drive" or settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        return GoogleDriveStorage()
    return LocalStorage()
