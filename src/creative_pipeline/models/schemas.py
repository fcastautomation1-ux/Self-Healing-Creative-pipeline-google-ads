from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class CreativeType(str, Enum):
    HEADLINE = "HEADLINE"
    DESCRIPTION = "DESCRIPTION"


class AssetType(str, Enum):
    HEADLINE = "HEADLINE"
    DESCRIPTION = "DESCRIPTION"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"


class TargetRatio(str, Enum):
    SQUARE = "SQUARE"         # 1:1
    LANDSCAPE = "LANDSCAPE"   # 1.91:1
    PORTRAIT = "PORTRAIT"     # 4:5 (or 9:16)


class VideoStatus(str, Enum):
    PUBLIC = "PUBLIC"
    UNLISTED = "UNLISTED"
    PRIVATE = "PRIVATE"
    DELETED = "DELETED"
    NOT_FOUND = "NOT_FOUND"
    NOT_EMBEDDABLE = "NOT_EMBEDDABLE"
    INVALID_URL = "INVALID_URL"


# ---------------------------------------------------------------------------
# Module 1: Text Sanitizer Models
# ---------------------------------------------------------------------------

class TextSanitizeRequest(BaseModel):
    creative_type: CreativeType = Field(..., description="HEADLINE or DESCRIPTION")
    text: str = Field(..., description="Input text to sanitize and validate")
    preserve_acronyms: bool = Field(True, description="Whether to keep common acronyms (e.g. US, AI) uppercase")
    max_length: Optional[int] = Field(None, description="Custom character limit override")

    model_config = {
        "json_schema_extra": {
            "example": {
                "creative_type": "HEADLINE",
                "text": "PHOTO EDITOR #1 📸 BEST APP EVER!!!"
            }
        }
    }


class TextSanitizeResponse(BaseModel):
    valid: bool
    original_text: str
    cleaned_text: str
    was_modified: bool
    modifications: List[str]
    char_count: int
    max_allowed: int


class BulkTextSanitizeRequest(BaseModel):
    creative_type: CreativeType = Field(CreativeType.HEADLINE)
    texts: List[str] = Field(..., description="List of raw texts or lines pasted from Excel")
    preserve_acronyms: bool = Field(True, description="Whether to keep common acronyms uppercase")
    max_length: Optional[int] = Field(None, description="Custom character limit override")


class BulkTextSanitizeResponse(BaseModel):
    total_items: int
    compliant_items: int
    modified_items: int
    results: List[TextSanitizeResponse]


# ---------------------------------------------------------------------------
# Module 2: Image Processing Models
# ---------------------------------------------------------------------------

class ImageProcessRequest(BaseModel):
    image_url: Optional[str] = Field(None, description="Direct URL or Google Drive link to image")
    target_ratios: List[TargetRatio] = Field(
        default=[TargetRatio.SQUARE, TargetRatio.LANDSCAPE, TargetRatio.PORTRAIT],
        description="Target Google Ads orientations to generate"
    )
    destination_folder_id: Optional[str] = Field(None, description="Google Drive folder ID if using Drive storage")
    portrait_aspect: str = Field("4:5", description="'4:5' or '9:16'")

    model_config = {
        "json_schema_extra": {
            "example": {
                "image_url": "https://images.unsplash.com/photo-1579783902614-a3fb3927b675",
                "target_ratios": ["SQUARE", "LANDSCAPE", "PORTRAIT"],
                "destination_folder_id": "optional_folder_id"
            }
        }
    }


class OriginalImageMeta(BaseModel):
    dimensions: str
    size_mb: float
    format: str


class ProcessedImageOutput(BaseModel):
    ratio: str
    dimensions: str
    url: str
    size_mb: float


class ImageProcessResponse(BaseModel):
    status: str
    original: OriginalImageMeta
    outputs: List[ProcessedImageOutput]


class BulkImageZipItem(BaseModel):
    filename: str
    original: OriginalImageMeta
    outputs: List[ProcessedImageOutput]


class BulkImageZipResponse(BaseModel):
    total_images_processed: int
    total_crops_generated: int
    zip_download_url: Optional[str] = None
    items: List[BulkImageZipItem]


# ---------------------------------------------------------------------------
# Module 3: Video Audit Models
# ---------------------------------------------------------------------------

class VideoAuditRequest(BaseModel):
    video_url: str = Field(..., description="YouTube video URL to audit")

    model_config = {
        "json_schema_extra": {
            "example": {
                "video_url": "https://www.youtube.com/watch?v=sample123"
            }
        }
    }


class VideoAuditResponse(BaseModel):
    video_id: Optional[str]
    is_usable: bool
    status: str
    reason: str
    action: str  # "KEEP_IN_QUEUE" or "DROP_FROM_QUEUE"


class BulkVideoAuditRequest(BaseModel):
    video_urls: List[str] = Field(..., description="List of YouTube video URLs to audit in bulk")


class BulkVideoAuditResponse(BaseModel):
    total_submitted: int
    ready_count: int
    dropped_count: int
    results: List[VideoAuditResponse]


# ---------------------------------------------------------------------------
# Module 4: Batch Pipeline Models
# ---------------------------------------------------------------------------

class BatchAssetInput(BaseModel):
    type: AssetType
    content: str
    orientation: Optional[str] = None


class BatchAssetReady(BaseModel):
    type: AssetType
    content: str
    orientation: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class BatchAssetDropped(BaseModel):
    type: AssetType
    content: str
    reason: str


class BatchMetrics(BaseModel):
    submitted: int
    generated_ready: int
    dropped: int


class BatchPipelineRequest(BaseModel):
    ad_group_alias: str = Field(..., description="Ad Group or Campaign alias")
    assets: List[BatchAssetInput]
    destination_folder_id: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "ad_group_alias": "Photo_Editor_US + Android",
                "assets": [
                    {"type": "HEADLINE", "content": "EDIT PHOTOS 📸"},
                    {"type": "DESCRIPTION", "content": "Fast & Easy photo editing tool at home..."},
                    {"type": "IMAGE", "content": "https://images.unsplash.com/photo-1579783902614-a3fb3927b675"},
                    {"type": "VIDEO", "content": "https://www.youtube.com/watch?v=invalid_or_private"}
                ]
            }
        }
    }


class BatchPipelineResponse(BaseModel):
    ad_group_alias: str
    ready_to_upload: List[BatchAssetReady]
    dropped_assets: List[BatchAssetDropped]
    metrics: BatchMetrics
