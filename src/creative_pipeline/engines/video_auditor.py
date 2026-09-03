import logging
import re
from typing import Optional, Tuple

import httpx

from creative_pipeline.config import settings
from creative_pipeline.models.schemas import (
    VideoAuditRequest,
    VideoAuditResponse,
    VideoStatus,
)

logger = logging.getLogger(__name__)


class VideoAuditor:
    """Module 3: Video Health Auditor & Filter ('Video Cleaner')."""

    # Stricter YouTube video ID regex pattern
    YOUTUBE_ID_PATTERN = re.compile(
        r"(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?.*?v=|embed\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})",
        re.IGNORECASE,
    )

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.YOUTUBE_API_KEY
        self._youtube_client = None
        if self.api_key:
            self._init_youtube_client()

    def _init_youtube_client(self):
        try:
            from googleapiclient.discovery import build
            self._youtube_client = build("youtube", "v3", developerKey=self.api_key, cache_discovery=False)
            logger.info("YouTube Data API v3 client initialized.")
        except Exception as e:
            logger.warning(f"Could not initialize YouTube API client: {e}")
            self._youtube_client = None

    def extract_video_id(self, url: str) -> Optional[str]:
        """Extracts 11-character YouTube video ID from various URL formats."""
        clean_url = url.strip()
        # Check if input is directly an 11-char video ID
        if re.fullmatch(r"[a-zA-Z0-9_-]{11}", clean_url):
            return clean_url

        match = self.YOUTUBE_ID_PATTERN.search(clean_url)
        if match:
            return match.group(1)
        return None

    async def audit_video(self, request: VideoAuditRequest) -> VideoAuditResponse:
        """Audits video accessibility and embeddability."""
        video_id = self.extract_video_id(request.video_url)
        if not video_id:
            return VideoAuditResponse(
                video_id=None,
                is_usable=False,
                status=VideoStatus.INVALID_URL.value,
                reason="Invalid YouTube URL or video ID format.",
                action="DROP_FROM_QUEUE",
            )

        # Mode A: Use YouTube Data API v3 if configured
        if self._youtube_client:
            try:
                return await self._audit_via_api(video_id)
            except Exception as e:
                logger.warning(
                    f"YouTube API call failed: {e}. Falling back to oEmbed probe."
                )

        # Mode B: Zero-config oEmbed + HTTP probe fallback
        return await self._audit_via_oembed(video_id)

    async def _audit_via_api(self, video_id: str) -> VideoAuditResponse:
        """Audits video using official YouTube Data API v3."""
        # Note: discovery API is synchronous, run in thread pool if needed
        import anyio

        def _fetch():
            return (
                self._youtube_client.videos()
                .list(part="status,snippet", id=video_id)
                .execute()
            )

        resp = await anyio.to_thread.run_sync(_fetch)
        items = resp.get("items", [])

        if not items:
            return VideoAuditResponse(
                video_id=video_id,
                is_usable=False,
                status=VideoStatus.NOT_FOUND.value,
                reason="Video not found or deleted on YouTube.",
                action="DROP_FROM_QUEUE",
            )

        item = items[0]
        status_info = item.get("status", {})
        privacy = status_info.get("privacyStatus", "unknown").upper()
        embeddable = status_info.get("embeddable", False)

        if privacy == "PRIVATE":
            return VideoAuditResponse(
                video_id=video_id,
                is_usable=False,
                status=VideoStatus.PRIVATE.value,
                reason="Video is Private. Please change visibility to Unlisted or Public in YouTube Studio.",
                action="DROP_FROM_QUEUE",
            )

        if not embeddable:
            return VideoAuditResponse(
                video_id=video_id,
                is_usable=False,
                status=VideoStatus.NOT_EMBEDDABLE.value,
                reason="Video embedding is disabled by the owner. Google Ads requires embeddable videos.",
                action="DROP_FROM_QUEUE",
            )

        status_val = (
            VideoStatus.PUBLIC.value if privacy == "PUBLIC" else VideoStatus.UNLISTED.value
        )
        return VideoAuditResponse(
            video_id=video_id,
            is_usable=True,
            status=status_val,
            reason=f"Video is {status_val.lower()} and embeddable.",
            action="KEEP_IN_QUEUE",
        )

    async def _audit_via_oembed(self, video_id: str) -> VideoAuditResponse:
        """Audits video using YouTube oEmbed endpoint and HTTP response codes."""
        oembed_url = (
            f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        )
        
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            try:
                resp = await client.get(oembed_url)
                
                if resp.status_code == 200:
                    data = resp.json()
                    title = data.get("title", "Video")
                    return VideoAuditResponse(
                        video_id=video_id,
                        is_usable=True,
                        status=VideoStatus.PUBLIC.value,
                        reason=f"Video is accessible ('{title}') and embeddable.",
                        action="KEEP_IN_QUEUE",
                    )
                elif resp.status_code == 401 or resp.status_code == 403:
                    # 401 Unauthorized or 403 Forbidden indicates private or embed restricted
                    return VideoAuditResponse(
                        video_id=video_id,
                        is_usable=False,
                        status=VideoStatus.PRIVATE.value,
                        reason="Video is Private or embedding is disabled.",
                        action="DROP_FROM_QUEUE",
                    )
                elif resp.status_code == 404:
                    return VideoAuditResponse(
                        video_id=video_id,
                        is_usable=False,
                        status=VideoStatus.DELETED.value,
                        reason="Video was deleted or does not exist.",
                        action="DROP_FROM_QUEUE",
                    )
                else:
                    return VideoAuditResponse(
                        video_id=video_id,
                        is_usable=False,
                        status=VideoStatus.NOT_FOUND.value,
                        reason=f"YouTube returned HTTP status {resp.status_code}.",
                        action="DROP_FROM_QUEUE",
                    )

            except httpx.RequestError as exc:
                logger.warning(f"Error querying oEmbed for video {video_id}: {exc}")
                return VideoAuditResponse(
                    video_id=video_id,
                    is_usable=False,
                    status=VideoStatus.NOT_FOUND.value,
                    reason=f"Network error querying YouTube status: {exc}",
                    action="DROP_FROM_QUEUE",
                )
