from functools import lru_cache
from creative_pipeline.engines.image_cropper import ImageCropper
from creative_pipeline.engines.text_sanitizer import TextSanitizer
from creative_pipeline.engines.video_auditor import VideoAuditor
from creative_pipeline.orchestrator.pipeline import PipelineOrchestrator
from creative_pipeline.storage import get_storage
from creative_pipeline.storage.base import BaseStorage


@lru_cache()
def get_storage_dep() -> BaseStorage:
    return get_storage()


@lru_cache()
def get_text_sanitizer() -> TextSanitizer:
    return TextSanitizer()


@lru_cache()
def get_image_cropper() -> ImageCropper:
    return ImageCropper(storage=get_storage_dep())


@lru_cache()
def get_video_auditor() -> VideoAuditor:
    return VideoAuditor()


@lru_cache()
def get_orchestrator() -> PipelineOrchestrator:
    return PipelineOrchestrator(
        text_sanitizer=get_text_sanitizer(),
        image_cropper=get_image_cropper(),
        video_auditor=get_video_auditor(),
    )
