import logging
from typing import List, Optional

from creative_pipeline.engines.image_cropper import ImageCropper
from creative_pipeline.engines.text_sanitizer import TextSanitizer
from creative_pipeline.engines.video_auditor import VideoAuditor
from creative_pipeline.models.schemas import (
    AssetType,
    BatchAssetDropped,
    BatchAssetInput,
    BatchAssetReady,
    BatchMetrics,
    BatchPipelineRequest,
    BatchPipelineResponse,
    CreativeType,
    TargetRatio,
    TextSanitizeRequest,
    VideoAuditRequest,
)

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Module 4: Batch Pipeline Orchestrator."""

    def __init__(
        self,
        text_sanitizer: Optional[TextSanitizer] = None,
        image_cropper: Optional[ImageCropper] = None,
        video_auditor: Optional[VideoAuditor] = None,
    ):
        self.text_sanitizer = text_sanitizer or TextSanitizer()
        self.image_cropper = image_cropper or ImageCropper()
        self.video_auditor = video_auditor or VideoAuditor()

    async def process_batch(
        self, request: BatchPipelineRequest
    ) -> BatchPipelineResponse:
        """Processes mixed asset batch and produces clean ready assets and dropped report."""
        ready_assets: List[BatchAssetReady] = []
        dropped_assets: List[BatchAssetDropped] = []
        submitted_count = len(request.assets)

        for asset in request.assets:
            try:
                if asset.type == AssetType.HEADLINE:
                    await self._handle_headline(asset, ready_assets, dropped_assets)
                elif asset.type == AssetType.DESCRIPTION:
                    await self._handle_description(asset, ready_assets, dropped_assets)
                elif asset.type == AssetType.IMAGE:
                    await self._handle_image(
                        asset,
                        request.destination_folder_id,
                        ready_assets,
                        dropped_assets,
                    )
                elif asset.type == AssetType.VIDEO:
                    await self._handle_video(asset, ready_assets, dropped_assets)
                else:
                    dropped_assets.append(
                        BatchAssetDropped(
                            type=asset.type,
                            content=asset.content,
                            reason=f"Unsupported asset type: {asset.type}",
                        )
                    )
            except Exception as exc:
                logger.error(f"Unexpected error processing asset {asset}: {exc}")
                dropped_assets.append(
                    BatchAssetDropped(
                        type=asset.type,
                        content=asset.content,
                        reason=f"Processing exception: {str(exc)}",
                    )
                )

        metrics = BatchMetrics(
            submitted=submitted_count,
            generated_ready=len(ready_assets),
            dropped=len(dropped_assets),
        )

        return BatchPipelineResponse(
            ad_group_alias=request.ad_group_alias,
            ready_to_upload=ready_assets,
            dropped_assets=dropped_assets,
            metrics=metrics,
        )

    async def _handle_headline(
        self,
        asset: BatchAssetInput,
        ready_assets: List[BatchAssetReady],
        dropped_assets: List[BatchAssetDropped],
    ):
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE,
            text=asset.content,
        )
        res = self.text_sanitizer.sanitize(req)
        if res.valid and res.cleaned_text.strip():
            ready_assets.append(
                BatchAssetReady(
                    type=AssetType.HEADLINE,
                    content=res.cleaned_text,
                    metadata={"modifications": res.modifications, "char_count": res.char_count},
                )
            )
        else:
            dropped_assets.append(
                BatchAssetDropped(
                    type=AssetType.HEADLINE,
                    content=asset.content,
                    reason="Headline invalid or empty after sanitization",
                )
            )

    async def _handle_description(
        self,
        asset: BatchAssetInput,
        ready_assets: List[BatchAssetReady],
        dropped_assets: List[BatchAssetDropped],
    ):
        req = TextSanitizeRequest(
            creative_type=CreativeType.DESCRIPTION,
            text=asset.content,
        )
        res = self.text_sanitizer.sanitize(req)
        if res.valid and res.cleaned_text.strip():
            ready_assets.append(
                BatchAssetReady(
                    type=AssetType.DESCRIPTION,
                    content=res.cleaned_text,
                    metadata={"modifications": res.modifications, "char_count": res.char_count},
                )
            )
        else:
            dropped_assets.append(
                BatchAssetDropped(
                    type=AssetType.DESCRIPTION,
                    content=asset.content,
                    reason="Description invalid or empty after sanitization",
                )
            )

    async def _handle_image(
        self,
        asset: BatchAssetInput,
        destination_folder_id: Optional[str],
        ready_assets: List[BatchAssetReady],
        dropped_assets: List[BatchAssetDropped],
    ):
        try:
            # Download image bytes
            image_bytes = await self.image_cropper.fetch_image_bytes(asset.content)
            
            # Determine target ratios
            if asset.orientation:
                ratio_name = asset.orientation.upper()
                if ratio_name in TargetRatio.__members__:
                    target_ratios = [TargetRatio[ratio_name]]
                else:
                    target_ratios = [
                        TargetRatio.SQUARE,
                        TargetRatio.LANDSCAPE,
                        TargetRatio.PORTRAIT,
                    ]
            else:
                target_ratios = [
                    TargetRatio.SQUARE,
                    TargetRatio.LANDSCAPE,
                    TargetRatio.PORTRAIT,
                ]

            process_res = await self.image_cropper.process_image(
                image_bytes=image_bytes,
                target_ratios=target_ratios,
                destination_folder_id=destination_folder_id,
            )

            for output in process_res.outputs:
                ready_assets.append(
                    BatchAssetReady(
                        type=AssetType.IMAGE,
                        content=output.url,
                        orientation=output.ratio,
                        metadata={
                            "dimensions": output.dimensions,
                            "size_mb": output.size_mb,
                            "source_url": asset.content,
                        },
                    )
                )

        except Exception as exc:
            logger.warning(f"Failed to process image {asset.content}: {exc}")
            dropped_assets.append(
                BatchAssetDropped(
                    type=AssetType.IMAGE,
                    content=asset.content,
                    reason=f"Failed to fetch or crop image: {str(exc)}",
                )
            )

    async def _handle_video(
        self,
        asset: BatchAssetInput,
        ready_assets: List[BatchAssetReady],
        dropped_assets: List[BatchAssetDropped],
    ):
        req = VideoAuditRequest(video_url=asset.content)
        audit_res = await self.video_auditor.audit_video(req)
        if audit_res.is_usable:
            ready_assets.append(
                BatchAssetReady(
                    type=AssetType.VIDEO,
                    content=asset.content,
                    metadata={
                        "video_id": audit_res.video_id,
                        "status": audit_res.status,
                        "reason": audit_res.reason,
                    },
                )
            )
        else:
            dropped_assets.append(
                BatchAssetDropped(
                    type=AssetType.VIDEO,
                    content=asset.content,
                    reason=audit_res.reason,
                )
            )
