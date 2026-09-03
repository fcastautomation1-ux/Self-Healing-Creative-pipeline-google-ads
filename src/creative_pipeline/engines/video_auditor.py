import json
import logging
import re
from typing import Optional, Tuple

import httpx

from creative_pipeline.models.schemas import (
    BulkVideoAuditRequest,
    BulkVideoAuditResponse,
    VideoAuditRequest,
    VideoAuditResponse,
    VideoStatus,
)

logger = logging.getLogger(__name__)


class VideoAuditor:
    """Module 3: Pure-Code Video Health Auditor & Filter ('Video Cleaner').

    Performs video verification via pure code HTTP inspection and metadata analysis
    WITHOUT requiring any external YouTube API keys or Google Cloud credentials.
    """

    # Stricter YouTube video ID regex pattern
    YOUTUBE_ID_PATTERN = re.compile(
        r"(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com\/(?:watch\?.*?v=|embed\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})",
        re.IGNORECASE,
    )

    PLAYER_RESPONSE_PATTERN = re.compile(
        r"ytInitialPlayerResponse\s*=\s*({.+?});", re.DOTALL
    )

    def __init__(self, api_key: Optional[str] = None):
        # Kept for backward compatibility if passed, but pure code mode is default
        self.api_key = api_key

    def extract_video_id(self, url: str) -> Optional[str]:
        """Extracts 11-character YouTube video ID from various URL formats via pure regex."""
        clean_url = url.strip()
        # Check if input is directly an 11-char video ID
        if re.fullmatch(r"[a-zA-Z0-9_-]{11}", clean_url):
            return clean_url

        match = self.YOUTUBE_ID_PATTERN.search(clean_url)
        if match:
            return match.group(1)
        return None

    async def audit_video(self, request: VideoAuditRequest) -> VideoAuditResponse:
        """Audits video accessibility and embeddability using 100% pure code."""
        video_id = self.extract_video_id(request.video_url)
        if not video_id:
            return VideoAuditResponse(
                video_id=None,
                is_usable=False,
                status=VideoStatus.INVALID_URL.value,
                reason="Invalid YouTube URL or video ID format.",
                action="DROP_FROM_QUEUE",
            )

        # Pure Code Step 1: Probe oEmbed public protocol (Zero API Key needed)
        oembed_res = await self._probe_oembed(video_id)
        if oembed_res is not None:
            return oembed_res

        # Pure Code Step 2: Probe YouTube Watch Page HTML & Player JSON
        return await self._probe_html_player(video_id)

    async def _probe_oembed(self, video_id: str) -> Optional[VideoAuditResponse]:
        """Inspects YouTube oEmbed endpoint (100% free, pure HTTP, zero API key)."""
        oembed_url = (
            f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            try:
                resp = await client.get(oembed_url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    title = data.get("title", "Video")
                    return VideoAuditResponse(
                        video_id=video_id,
                        is_usable=True,
                        status=VideoStatus.PUBLIC.value,
                        reason=f"Video is public and embeddable ('{title}'). Verified with pure code.",
                        action="KEEP_IN_QUEUE",
                    )
                elif resp.status_code in (401, 403):
                    return VideoAuditResponse(
                        video_id=video_id,
                        is_usable=False,
                        status=VideoStatus.PRIVATE.value,
                        reason="Video is Private or embedding is prohibited by the owner.",
                        action="DROP_FROM_QUEUE",
                    )
                elif resp.status_code == 404:
                    return VideoAuditResponse(
                        video_id=video_id,
                        is_usable=False,
                        status=VideoStatus.DELETED.value,
                        reason="Video was deleted or does not exist on YouTube.",
                        action="DROP_FROM_QUEUE",
                    )
            except Exception as exc:
                logger.debug(f"oEmbed probe skipped: {exc}")

        return None

    async def _probe_html_player(self, video_id: str) -> VideoAuditResponse:
        """Parses YouTube initial player response directly from page HTML via pure regex."""
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            try:
                resp = await client.get(watch_url, headers=headers)
                if resp.status_code == 404:
                    return VideoAuditResponse(
                        video_id=video_id,
                        is_usable=False,
                        status=VideoStatus.DELETED.value,
                        reason="Video not found or deleted (HTTP 404).",
                        action="DROP_FROM_QUEUE",
                    )

                html = resp.text
                match = self.PLAYER_RESPONSE_PATTERN.search(html)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        playability = data.get("playabilityStatus", {})
                        status = playability.get("status", "").upper()
                        reason = playability.get("reason", "")

                        if status == "OK":
                            return VideoAuditResponse(
                                video_id=video_id,
                                is_usable=True,
                                status=VideoStatus.PUBLIC.value,
                                reason="Video is playable and embeddable. Verified with pure code.",
                                action="KEEP_IN_QUEUE",
                            )
                        elif status in ("LOGIN_REQUIRED", "PRIVATE"):
                            return VideoAuditResponse(
                                video_id=video_id,
                                is_usable=False,
                                status=VideoStatus.PRIVATE.value,
                                reason=reason or "Video is Private. Please change visibility to Unlisted or Public.",
                                action="DROP_FROM_QUEUE",
                            )
                        elif status in ("UNPLAYABLE", "ERROR"):
                            return VideoAuditResponse(
                                video_id=video_id,
                                is_usable=False,
                                status=VideoStatus.DELETED.value,
                                reason=reason or "Video is unplayable or removed.",
                                action="DROP_FROM_QUEUE",
                            )
                    except json.JSONDecodeError:
                        pass

                # If status 200 and no restriction found
                if resp.status_code == 200:
                    return VideoAuditResponse(
                        video_id=video_id,
                        is_usable=True,
                        status=VideoStatus.PUBLIC.value,
                        reason="Video is accessible. Verified via pure code HTTP probe.",
                        action="KEEP_IN_QUEUE",
                    )

                return VideoAuditResponse(
                    video_id=video_id,
                    is_usable=False,
                    status=VideoStatus.NOT_FOUND.value,
                    reason=f"HTTP status {resp.status_code} received from video probe.",
                    action="DROP_FROM_QUEUE",
                )

            except Exception as exc:
                logger.warning(f"Error during pure code video audit for {video_id}: {exc}")
                return VideoAuditResponse(
                    video_id=video_id,
                    is_usable=False,
                    status=VideoStatus.NOT_FOUND.value,
                    reason=f"Probe failed: {str(exc)}",
                    action="DROP_FROM_QUEUE",
                )

    async def audit_videos_bulk(
        self, request: BulkVideoAuditRequest
    ) -> BulkVideoAuditResponse:
        """Audits an entire list of YouTube video URLs in bulk using pure code HTTP inspection."""
        import asyncio

        tasks = [
            self.audit_video(VideoAuditRequest(video_url=url))
            for url in request.video_urls
            if url.strip()
        ]
        results = await asyncio.gather(*tasks) if tasks else []
        ready_count = sum(1 for r in results if r.is_usable)
        dropped_count = len(results) - ready_count

        return BulkVideoAuditResponse(
            total_submitted=len(results),
            ready_count=ready_count,
            dropped_count=dropped_count,
            results=list(results),
        )
