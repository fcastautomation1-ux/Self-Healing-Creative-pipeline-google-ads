import os
from pathlib import Path
from typing import Optional
from creative_pipeline.config import settings
from creative_pipeline.storage.base import BaseStorage


class LocalStorage(BaseStorage):
    """Local disk storage with static URL serving."""

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.storage_dir = Path(storage_dir or settings.LOCAL_STORAGE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = (base_url or settings.BASE_URL).rstrip("/")

    async def save(
        self,
        data: bytes,
        filename: str,
        content_type: str = "image/jpeg",
        folder_id: Optional[str] = None,
    ) -> str:
        # If folder_id provided, create subfolder
        target_dir = self.storage_dir
        if folder_id:
            target_dir = self.storage_dir / folder_id
            target_dir.mkdir(parents=True, exist_ok=True)

        file_path = target_dir / filename
        with open(file_path, "wb") as f:
            f.write(data)

        if folder_id:
            return f"{self.base_url}/assets/{folder_id}/{filename}"
        return f"{self.base_url}/assets/{filename}"
