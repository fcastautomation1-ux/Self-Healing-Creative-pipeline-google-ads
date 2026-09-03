from fastapi import APIRouter, Depends
from creative_pipeline.api.deps import get_video_auditor
from creative_pipeline.engines.video_auditor import VideoAuditor
from creative_pipeline.models.schemas import (
    VideoAuditRequest,
    VideoAuditResponse,
)

router = APIRouter(prefix="/v1/audit", tags=["Video Health Auditor"])


@router.post(
    "/video",
    response_model=VideoAuditResponse,
    summary="Verify YouTube video accessibility, privacy, and embeddability",
)
async def audit_video(
    request: VideoAuditRequest,
    auditor: VideoAuditor = Depends(get_video_auditor),
) -> VideoAuditResponse:
    """Checks whether a YouTube video is valid, public/unlisted, and embeddable

    for Google Ads campaigns. Purges private, deleted, or unembeddable videos.
    """
    return await auditor.audit_video(request)
