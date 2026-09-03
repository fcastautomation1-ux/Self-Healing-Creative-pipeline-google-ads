from abc import ABC, abstractmethod
from typing import Optional


class BaseStorage(ABC):
    """Abstract storage provider interface."""

    @abstractmethod
    async def save(
        self,
        data: bytes,
        filename: str,
        content_type: str = "image/jpeg",
        folder_id: Optional[str] = None,
    ) -> str:
        """Save file bytes and return a publicly accessible or shareable URL."""
        pass
