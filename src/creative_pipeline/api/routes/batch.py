from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from creative_pipeline.adapters.sheets import SheetsAdapter
from creative_pipeline.api.deps import get_orchestrator
from creative_pipeline.models.schemas import (
    BatchPipelineRequest,
    BatchPipelineResponse,
)
from creative_pipeline.orchestrator.pipeline import PipelineOrchestrator

router = APIRouter(prefix="/v1/pipeline", tags=["Batch Pipeline Orchestration"])


@router.post(
    "/batch",
    response_model=BatchPipelineResponse,
    summary="Process complete mixed-asset payload for Google Ads upload",
)
async def process_batch(
    request: BatchPipelineRequest,
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
) -> BatchPipelineResponse:
    """Takes mixed rough assets (Headlines, Descriptions, Images, Videos),

    runs them through Text Sanitizer, Image Auto-Cropper, and Video Auditor,
    and returns production-ready assets alongside a dropped assets report.
    """
    return await orchestrator.process_batch(request)


@router.post(
    "/csv",
    summary="Upload raw CSV file and download cleaned Google Ads ready CSV",
)
async def process_csv_file(
    file: UploadFile = File(..., description="CSV file with columns ad_group_alias, asset_type, content"),
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
):
    """Processes a CSV sheet of assets and outputs a consolidated CSV

    containing both ready assets and dropped assets report.
    """
    content = await file.read()
    try:
        csv_text = content.decode("utf-8")
    except UnicodeDecodeError:
        csv_text = content.decode("latin-1")

    requests = SheetsAdapter.parse_csv_to_requests(csv_text)
    if not requests:
        raise HTTPException(
            status_code=400,
            detail="Could not parse valid asset rows from CSV. Expected columns: ad_group_alias, asset_type, content",
        )

    all_ready = []
    all_dropped = []
    alias = requests[0].ad_group_alias

    for req in requests:
        res = await orchestrator.process_batch(req)
        all_ready.extend(res.ready_to_upload)
        all_dropped.extend(res.dropped_assets)

    csv_output = SheetsAdapter.export_to_csv(alias, all_ready, all_dropped)
    return Response(
        content=csv_output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=cleaned_assets_{alias}.csv"},
    )
