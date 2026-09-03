from unittest.mock import MagicMock, patch
import pytest

from creative_pipeline.engines.video_auditor import VideoAuditor
from creative_pipeline.models.schemas import VideoAuditRequest, VideoStatus


@pytest.fixture
def auditor():
    return VideoAuditor()


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


class TestPureCodeVideoAuditor:
    @pytest.mark.asyncio
    async def test_oembed_200_public_success(self, auditor):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"title": "Google Ads Showcase Video"}

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            req = VideoAuditRequest(video_url="https://youtu.be/dQw4w9WgXcQ")
            res = await auditor.audit_video(req)
            assert res.is_usable is True
            assert res.status == "PUBLIC"
            assert res.action == "KEEP_IN_QUEUE"
            assert "Google Ads Showcase Video" in res.reason

    @pytest.mark.asyncio
    async def test_oembed_401_private_detected(self, auditor):
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            req = VideoAuditRequest(video_url="https://youtu.be/private1234")
            res = await auditor.audit_video(req)
            assert res.is_usable is False
            assert res.status == "PRIVATE"
            assert res.action == "DROP_FROM_QUEUE"

    @pytest.mark.asyncio
    async def test_oembed_404_deleted_detected(self, auditor):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            req = VideoAuditRequest(video_url="https://youtu.be/deleted1234")
            res = await auditor.audit_video(req)
            assert res.is_usable is False
            assert res.status == "DELETED"
            assert res.action == "DROP_FROM_QUEUE"

    @pytest.mark.asyncio
    async def test_html_player_response_private(self, auditor):
        # When oEmbed fails or is skipped, fallback inspects HTML player response
        mock_oembed = MagicMock()
        mock_oembed.status_code = 500

        mock_html = MagicMock()
        mock_html.status_code = 200
        mock_html.text = (
            '<html><script>var ytInitialPlayerResponse = {"playabilityStatus": '
            '{"status": "LOGIN_REQUIRED", "reason": "This video is private."}};</script></html>'
        )

        async def _mock_get(url, *args, **kwargs):
            if "oembed" in url:
                return mock_oembed
            return mock_html

        with patch("httpx.AsyncClient.get", side_effect=_mock_get):
            req = VideoAuditRequest(video_url="https://youtu.be/priv1234567")
            res = await auditor.audit_video(req)
            assert res.is_usable is False
            assert res.status == "PRIVATE"
            assert res.action == "DROP_FROM_QUEUE"

    @pytest.mark.asyncio
    async def test_html_player_response_ok(self, auditor):
        mock_oembed = MagicMock()
        mock_oembed.status_code = 500

        mock_html = MagicMock()
        mock_html.status_code = 200
        mock_html.text = (
            '<html><script>var ytInitialPlayerResponse = {"playabilityStatus": '
            '{"status": "OK"}};</script></html>'
        )

        async def _mock_get(url, *args, **kwargs):
            if "oembed" in url:
                return mock_oembed
            return mock_html

        with patch("httpx.AsyncClient.get", side_effect=_mock_get):
            req = VideoAuditRequest(video_url="https://youtu.be/public12345")
            res = await auditor.audit_video(req)
            assert res.is_usable is True
            assert res.status == "PUBLIC"
            assert res.action == "KEEP_IN_QUEUE"

    @pytest.mark.asyncio
    async def test_invalid_url_drop(self, auditor):
        req = VideoAuditRequest(video_url="http://invalid.com/notayoutubevid")
        res = await auditor.audit_video(req)
        assert res.is_usable is False
        assert res.status == VideoStatus.INVALID_URL.value
        assert res.action == "DROP_FROM_QUEUE"

    @pytest.mark.asyncio
    async def test_bulk_video_auditing(self, auditor):
        from creative_pipeline.models.schemas import BulkVideoAuditRequest

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"title": "Sample Title", "author_name": "Sample Author"}

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            req = BulkVideoAuditRequest(
                video_urls=[
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "https://youtu.be/dQw4w9WgXcQ",
                    "invalid_link_here",
                ]
            )
            res = await auditor.audit_videos_bulk(req)
            assert res.total_submitted == 3
            assert res.ready_count == 2
            assert res.dropped_count == 1
            assert len(res.results) == 3

