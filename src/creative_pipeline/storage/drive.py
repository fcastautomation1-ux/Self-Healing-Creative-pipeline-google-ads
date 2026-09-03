import io
import json
import logging
import os
from pathlib import Path
from typing import Optional

from creative_pipeline.config import settings
from creative_pipeline.storage.base import BaseStorage
from creative_pipeline.storage.local import LocalStorage

logger = logging.getLogger(__name__)


class GoogleDriveStorage(BaseStorage):
    """Google Drive storage provider using Service Account credentials."""

    def __init__(
        self,
        service_account_json: Optional[str] = None,
        default_folder_id: Optional[str] = None,
        fallback_storage: Optional[BaseStorage] = None,
    ):
        self.service_account_json = (
            service_account_json or settings.GOOGLE_SERVICE_ACCOUNT_JSON
        )
        self.default_folder_id = (
            default_folder_id or settings.GOOGLE_DRIVE_FOLDER_ID
        )
        self.fallback = fallback_storage or LocalStorage()
        self._service = None
        self._init_drive_client()

    def _init_drive_client(self):
        """Initializes Google Drive API service if credentials exist."""
        if not self.service_account_json:
            logger.info("No GOOGLE_SERVICE_ACCOUNT_JSON provided. Using LocalStorage fallback.")
            return

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            scopes = ["https://www.googleapis.com/auth/drive"]

            if os.path.isfile(self.service_account_json):
                creds = service_account.Credentials.from_service_account_file(
                    self.service_account_json, scopes=scopes
                )
            else:
                # Try parsing as raw JSON string
                info = json.loads(self.service_account_json)
                creds = service_account.Credentials.from_service_account_info(
                    info, scopes=scopes
                )

            self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
            logger.info("Google Drive client successfully authenticated.")
        except Exception as e:
            logger.warning(
                f"Failed to initialize Google Drive client: {e}. Falling back to LocalStorage."
            )
            self._service = None

    async def save(
        self,
        data: bytes,
        filename: str,
        content_type: str = "image/jpeg",
        folder_id: Optional[str] = None,
    ) -> str:
        if self._service is None:
            return await self.fallback.save(data, filename, content_type, folder_id)

        try:
            from googleapiclient.http import MediaIoBaseUpload

            target_folder = folder_id or self.default_folder_id
            file_metadata = {"name": filename}
            if target_folder:
                file_metadata["parents"] = [target_folder]

            media = MediaIoBaseUpload(
                io.BytesIO(data), mimetype=content_type, resumable=True
            )

            file = (
                self._service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, webViewLink, webContentLink",
                )
                .execute()
            )

            file_id = file.get("id")

            # Make public read-only for Google Ads ingest
            try:
                self._service.permissions().create(
                    fileId=file_id,
                    body={"type": "anyone", "role": "reader"},
                    fields="id",
                ).execute()
            except Exception as perm_err:
                logger.warning(f"Could not set public permission on file {file_id}: {perm_err}")

            return file.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"

        except Exception as e:
            logger.error(f"Google Drive upload error: {e}. Using fallback storage.")
            return await self.fallback.save(data, filename, content_type, folder_id)
