from unittest.mock import MagicMock, patch
import pytest

from creative_pipeline.engines.video_auditor import VideoAuditor
from creative_pipeline.models.schemas import VideoAuditRequest, VideoStatus


@pytest.fixture
def auditor():
    return VideoAuditor(api_key=None)


class TestVideoIdExtraction:
    @pytest.mark.parametrize(
        "url,expected_id",
        [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://m.youtube.com/watch?v=dQw4w9WgXcQ&feature=share", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ],
    )
    def test_valid_urls_extract_id(self, auditor, url, expected_id):
        assert auditor.extract_video_id(url) == expected_id

    def test_invalid_url_returns_none(self, auditor):
        assert auditor.extract_video_id("https://vimeo.com/12345678") is None
        assert auditor.extract_video_id("just some random text") is None


class TestVideoAuditorApiMode:
    @pytest.mark.asyncio
    async def test_api_public_and_embeddable(self):
        auditor = VideoAuditor(api_key="mock_key")
        mock_client = MagicMock()
        mock_videos = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "items": [
                {
                    "id": "dQw4w9WgXcQ",
                    "status": {"privacyStatus": "public", "embeddable": True},
                }
            ]
        }
        mock_videos.list.return_value = mock_list
        mock_client.videos.return_value = mock_videos
        auditor._youtube_client = mock_client

        req = VideoAuditRequest(video_url="https://youtu.be/dQw4w9WgXcQ")
        res = await auditor.audit_video(req)
        assert res.is_usable is True
        assert res.status == "PUBLIC"
        assert res.action == "KEEP_IN_QUEUE"

    @pytest.mark.asyncio
    async def test_api_private_video(self):
        auditor = VideoAuditor(api_key="mock_key")
        mock_client = MagicMock()
        mock_videos = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "items": [
                {
                    "id": "private12345",
                    "status": {"privacyStatus": "private", "embeddable": True},
                }
            ]
        }
        mock_videos.list.return_value = mock_list
        mock_client.videos.return_value = mock_videos
        auditor._youtube_client = mock_client

        req = VideoAuditRequest(video_url="https://youtu.be/private12345")
        res = await auditor.audit_video(req)
        assert res.is_usable is False
        assert res.status == "PRIVATE"
        assert res.action == "DROP_FROM_QUEUE"
        assert "Private" in res.reason

    @pytest.mark.asyncio
    async def test_api_unembeddable_video(self):
        auditor = VideoAuditor(api_key="mock_key")
        mock_client = MagicMock()
        mock_videos = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "items": [
                {
                    "id": "noembed1234",
                    "status": {"privacyStatus": "public", "embeddable": False},
                }
            ]
        }
        mock_videos.list.return_value = mock_list
        mock_client.videos.return_value = mock_videos
        auditor._youtube_client = mock_client

        req = VideoAuditRequest(video_url="https://youtu.be/noembed12345")
        res = await auditor.audit_video(req)
        assert res.is_usable is False
        assert res.status == "NOT_EMBEDDABLE"
        assert res.action == "DROP_FROM_QUEUE"

    @pytest.mark.asyncio
    async def test_api_not_found(self):
        auditor = VideoAuditor(api_key="mock_key")
        mock_client = MagicMock()
        mock_videos = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {"items": []}
        mock_videos.list.return_value = mock_list
        mock_client.videos.return_value = mock_videos
        auditor._youtube_client = mock_client

        req = VideoAuditRequest(video_url="https://youtu.be/deleted1234")
        res = await auditor.audit_video(req)
        assert res.is_usable is False
        assert res.status == "NOT_FOUND"
        assert res.action == "DROP_FROM_QUEUE"


class TestVideoAuditorOEmbedFallback:
    @pytest.mark.asyncio
    async def test_oembed_200_public(self, auditor):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"title": "Cool Product Ad"}

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            req = VideoAuditRequest(video_url="https://youtu.be/dQw4w9WgXcQ")
            res = await auditor.audit_video(req)
            assert res.is_usable is True
            assert res.status == "PUBLIC"
            assert res.action == "KEEP_IN_QUEUE"
            assert "Cool Product Ad" in res.reason

    @pytest.mark.asyncio
    async def test_oembed_401_private(self, auditor):
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            req = VideoAuditRequest(video_url="https://youtu.be/private1234")
            res = await auditor.audit_video(req)
            assert res.is_usable is False
            assert res.status == "PRIVATE"
            assert res.action == "DROP_FROM_QUEUE"

    @pytest.mark.asyncio
    async def test_oembed_404_deleted(self, auditor):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            req = VideoAuditRequest(video_url="https://youtu.be/deleted1234")
            res = await auditor.audit_video(req)
            assert res.is_usable is False
            assert res.status == "DELETED"
            assert res.action == "DROP_FROM_QUEUE"

    @pytest.mark.asyncio
    async def test_invalid_url_drop(self, auditor):
        req = VideoAuditRequest(video_url="http://invalid.com/notayoutubevid")
        res = await auditor.audit_video(req)
        assert res.is_usable is False
        assert res.status == VideoStatus.INVALID_URL.value
        assert res.action == "DROP_FROM_QUEUE"
