from fastapi import APIRouter, Depends
from creative_pipeline.api.deps import get_text_sanitizer
from creative_pipeline.engines.text_sanitizer import TextSanitizer
from creative_pipeline.models.schemas import (
    BulkTextSanitizeRequest,
    BulkTextSanitizeResponse,
    TextSanitizeRequest,
    TextSanitizeResponse,
)

router = APIRouter(prefix="/v1/sanitize", tags=["Text Transformation Engine"])


@router.post(
    "/text",
    response_model=TextSanitizeResponse,
    summary="Sanitize and validate Google Ads headline or description copy",
)
async def sanitize_text(
    request: TextSanitizeRequest,
    sanitizer: TextSanitizer = Depends(get_text_sanitizer),
) -> TextSanitizeResponse:
    """Ingests raw un-vetted text copy and applies Google Ads editorial rules:

    - Removes emojis and pictographs
    - Strips prohibited punctuation/symbols (@, #, *, ~, ^, |, etc.)
    - Normalizes repetitive punctuation (headline exclamation marks, trailing dots)
    - Normalizes ALL-CAPS to Title Case or Sentence Case
    - Trims intelligently at word boundaries without breaking words
    """
    return sanitizer.sanitize(request)


@router.post(
    "/bulk",
    response_model=BulkTextSanitizeResponse,
    summary="Bulk sanitize a list or column of headlines/descriptions copied from Excel",
)
async def sanitize_bulk_text(
    request: BulkTextSanitizeRequest,
    sanitizer: TextSanitizer = Depends(get_text_sanitizer),
) -> BulkTextSanitizeResponse:
    """Ingests multiple rows copied from an Excel or Google Sheets column and auto-fixes every line individually."""
    return sanitizer.sanitize_bulk(request)
