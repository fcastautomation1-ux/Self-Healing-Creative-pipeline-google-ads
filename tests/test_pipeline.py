from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from creative_pipeline.adapters.sheets import SheetsAdapter
from creative_pipeline.engines.image_cropper import ImageCropper
from creative_pipeline.engines.text_sanitizer import TextSanitizer
from creative_pipeline.engines.video_auditor import VideoAuditor
from creative_pipeline.models.schemas import (
    AssetType,
    BatchAssetInput,
    BatchPipelineRequest,
    ImageProcessResponse,
    OriginalImageMeta,
    ProcessedImageOutput,
    VideoAuditResponse,
)
from creative_pipeline.orchestrator.pipeline import PipelineOrchestrator


@pytest.fixture
def mock_image_cropper():
    cropper = MagicMock(spec=ImageCropper)
    cropper.fetch_image_bytes = AsyncMock(return_value=b"fake_image_bytes")
    cropper.process_image = AsyncMock(
        return_value=ImageProcessResponse(
            status="success",
            original=OriginalImageMeta(
                dimensions="1920x1080", size_mb=1.5, format="JPEG"
            ),
            outputs=[
                ProcessedImageOutput(
                    ratio="SQUARE",
                    dimensions="1200x1200",
                    url="http://localhost:8000/assets/square.jpg",
                    size_mb=0.8,
                ),
                ProcessedImageOutput(
                    ratio="LANDSCAPE",
                    dimensions="1200x628",
                    url="http://localhost:8000/assets/landscape.jpg",
                    size_mb=0.6,
                ),
                ProcessedImageOutput(
                    ratio="PORTRAIT",
                    dimensions="1200x1500",
                    url="http://localhost:8000/assets/portrait.jpg",
                    size_mb=0.9,
                ),
            ],
        )
    )
    return cropper


@pytest.fixture
def mock_video_auditor():
    auditor = MagicMock(spec=VideoAuditor)

    async def _audit(req):
        if "private" in req.video_url:
            return VideoAuditResponse(
                video_id="private_vid",
                is_usable=False,
                status="PRIVATE",
                reason="Video is Private. Please change visibility to Unlisted or Public in YouTube Studio.",
                action="DROP_FROM_QUEUE",
            )
        else:
            return VideoAuditResponse(
                video_id="public_vid",
                is_usable=True,
                status="PUBLIC",
                reason="Video is public and embeddable.",
                action="KEEP_IN_QUEUE",
            )

    auditor.audit_video = AsyncMock(side_effect=_audit)
    return auditor


@pytest.fixture
def orchestrator(mock_image_cropper, mock_video_auditor):
    return PipelineOrchestrator(
        text_sanitizer=TextSanitizer(),
        image_cropper=mock_image_cropper,
        video_auditor=mock_video_auditor,
    )


class TestPipelineOrchestrator:
    @pytest.mark.asyncio
    async def test_full_batch_pipeline_spec_example(self, orchestrator):
        # Spec payload test:
        # 1 Headline, 1 Description, 1 Image, 1 Private Video
        req = BatchPipelineRequest(
            ad_group_alias="Photo_Editor_US + Android",
            assets=[
                BatchAssetInput(type=AssetType.HEADLINE, content="EDIT PHOTOS 📸"),
                BatchAssetInput(
                    type=AssetType.DESCRIPTION,
                    content="Fast & Easy photo editing tool at home...",
                ),
                BatchAssetInput(
                    type=AssetType.IMAGE,
                    content="https://drive.google.com/file/d/raw_img/view",
                ),
                BatchAssetInput(
                    type=AssetType.VIDEO,
                    content="https://youtube.com/watch?v=private_vid",
                ),
            ],
        )

        res = await orchestrator.process_batch(req)

        assert res.ad_group_alias == "Photo_Editor_US + Android"
        assert res.metrics.submitted == 4
        # Ready should have: 1 Headline + 1 Description + 3 Image ratios = 5
        assert res.metrics.generated_ready == 5
        assert res.metrics.dropped == 1

        # Verify Headline cleaned
        headline_assets = [a for a in res.ready_to_upload if a.type == AssetType.HEADLINE]
        assert len(headline_assets) == 1
        assert headline_assets[0].content == "Edit Photos"

        # Verify Description cleaned
        desc_assets = [a for a in res.ready_to_upload if a.type == AssetType.DESCRIPTION]
        assert len(desc_assets) == 1
        assert "Fast & Easy photo editing tool at home" in desc_assets[0].content

        # Verify Image generated 3 orientations
        img_assets = [a for a in res.ready_to_upload if a.type == AssetType.IMAGE]
        assert len(img_assets) == 3
        orientations = {a.orientation for a in img_assets}
        assert orientations == {"SQUARE", "LANDSCAPE", "PORTRAIT"}

        # Verify Video dropped
        assert len(res.dropped_assets) == 1
        assert res.dropped_assets[0].type == AssetType.VIDEO
        assert "Private" in res.dropped_assets[0].reason

    @pytest.mark.asyncio
    async def test_batch_with_valid_video_and_single_image_orientation(
        self, orchestrator, mock_image_cropper
    ):
        mock_image_cropper.process_image = AsyncMock(
            return_value=ImageProcessResponse(
                status="success",
                original=OriginalImageMeta(dimensions="1200x1200", size_mb=1.0, format="JPEG"),
                outputs=[
                    ProcessedImageOutput(
                        ratio="SQUARE",
                        dimensions="1200x1200",
                        url="http://localhost:8000/assets/sq.jpg",
                        size_mb=0.7,
                    )
                ],
            )
        )

        req = BatchPipelineRequest(
            ad_group_alias="Campaign_B",
            assets=[
                BatchAssetInput(
                    type=AssetType.IMAGE,
                    content="https://example.com/banner.jpg",
                    orientation="SQUARE",
                ),
                BatchAssetInput(
                    type=AssetType.VIDEO,
                    content="https://youtube.com/watch?v=public_vid",
                ),
            ],
        )

        res = await orchestrator.process_batch(req)
        assert res.metrics.submitted == 2
        assert res.metrics.generated_ready == 2
        assert res.metrics.dropped == 0


class TestSheetsAdapter:
    def test_csv_roundtrip_parsing_and_export(self):
        sample_csv = """ad_group_alias,asset_type,content,orientation
Photo_Editor_US,HEADLINE,BEST PHOTO APP 📸,
Photo_Editor_US,DESCRIPTION,Edit photos in seconds!,
Photo_Editor_US,IMAGE,https://example.com/photo.jpg,SQUARE
"""
        requests = SheetsAdapter.parse_csv_to_requests(sample_csv)
        assert len(requests) == 1
        req = requests[0]
        assert req.ad_group_alias == "Photo_Editor_US"
        assert len(req.assets) == 3

        # Test CSV export
        from creative_pipeline.models.schemas import BatchAssetReady, BatchAssetDropped

        ready = [
            BatchAssetReady(
                type=AssetType.HEADLINE, content="Best Photo App"
            ),
            BatchAssetReady(
                type=AssetType.IMAGE,
                content="http://localhost:8000/assets/img.jpg",
                orientation="SQUARE",
            ),
        ]
        dropped = [
            BatchAssetDropped(
                type=AssetType.VIDEO,
                content="https://youtube.com/watch?v=private",
                reason="Video is private",
            )
        ]

        csv_out = SheetsAdapter.export_to_csv("Photo_Editor_US", ready, dropped)
        assert "READY ASSETS" in csv_out
        assert "Best Photo App" in csv_out
        assert "DROPPED ASSETS" in csv_out
        assert "Video is private" in csv_out
