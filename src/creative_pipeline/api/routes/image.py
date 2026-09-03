from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from creative_pipeline.api.deps import get_image_cropper
from creative_pipeline.engines.image_cropper import ImageCropper
from creative_pipeline.models.schemas import (
    BulkImageZipItem,
    BulkImageZipResponse,
    ImageProcessRequest,
    ImageProcessResponse,
    TargetRatio,
)

router = APIRouter(prefix="/v1/process", tags=["Smart Visual Engine"])


@router.post(
    "/image",
    response_model=ImageProcessResponse,
    summary="Auto-crop and resize image from URL into Google Ads orientations",
)
async def process_image_url(
    request: ImageProcessRequest,
    cropper: ImageCropper = Depends(get_image_cropper),
) -> ImageProcessResponse:
    """Downloads an image from a URL (standard or Google Drive link) and auto-crops it

    into Google Ads standard orientations (1:1 Square, 1.91:1 Landscape, 4:5/9:16 Portrait)
    with saliency detection and automatic compression (< 5.0 MB).
    """
    if not request.image_url:
        raise HTTPException(status_code=400, detail="image_url is required")

    try:
        image_bytes = await cropper.fetch_image_bytes(request.image_url)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to download image from URL: {str(exc)}",
        )

    try:
        return await cropper.process_image(
            image_bytes=image_bytes,
            target_ratios=request.target_ratios,
            destination_folder_id=request.destination_folder_id,
            portrait_aspect=request.portrait_aspect,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process image: {str(exc)}",
        )


@router.post(
    "/image/upload",
    response_model=ImageProcessResponse,
    summary="Upload image file directly for auto-cropping and resizing",
)
async def process_image_upload(
    file: UploadFile = File(..., description="Raw image file (JPG, PNG, WebP)"),
    target_ratios: Optional[List[TargetRatio]] = Form(
        default=[TargetRatio.SQUARE, TargetRatio.LANDSCAPE, TargetRatio.PORTRAIT]
    ),
    destination_folder_id: Optional[str] = Form(None),
    portrait_aspect: str = Form("4:5"),
    cropper: ImageCropper = Depends(get_image_cropper),
) -> ImageProcessResponse:
    """Direct multipart file upload for image auto-cropping and resizing."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        return await cropper.process_image(
            image_bytes=content,
            target_ratios=target_ratios,
            destination_folder_id=destination_folder_id,
            portrait_aspect=portrait_aspect,
            filename_prefix=file.filename.rsplit(".", 1)[0] if file.filename else None,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process uploaded image: {str(exc)}",
        )


@router.post(
    "/images/zip",
    response_model=BulkImageZipResponse,
    summary="Upload a ZIP archive containing multiple images to auto-crop all banners in bulk",
)
async def process_images_zip_upload(
    file: UploadFile = File(..., description="ZIP archive containing raw marketing images"),
    target_ratios: Optional[List[TargetRatio]] = Form(
        default=[TargetRatio.SQUARE, TargetRatio.LANDSCAPE, TargetRatio.PORTRAIT]
    ),
    destination_folder_id: Optional[str] = Form(None),
    portrait_aspect: str = Form("4:5"),
    cropper: ImageCropper = Depends(get_image_cropper),
) -> BulkImageZipResponse:
    """Unpacks a ZIP archive of marketing banners and auto-crops every banner into

    Google Ads standard orientations (1:1, 1.91:1, 4:5/9:16) with compression < 5.0 MB.
    """
    import io
    import zipfile

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        zip_buf = io.BytesIO(content)
        with zipfile.ZipFile(zip_buf, "r") as zf:
            image_names = [
                n
                for n in zf.namelist()
                if not n.endswith("/")
                and not n.startswith("__MACOSX")
                and n.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ]
            if not image_names:
                raise HTTPException(
                    status_code=400,
                    detail="No supported images (.jpg, .png, .webp) found in the ZIP archive.",
                )

            items = []
            total_crops = 0
            for name in image_names:
                img_data = zf.read(name)
                prefix = name.rsplit(".", 1)[0].replace("/", "_")
                proc_res = await cropper.process_image(
                    image_bytes=img_data,
                    target_ratios=target_ratios,
                    destination_folder_id=destination_folder_id,
                    portrait_aspect=portrait_aspect,
                    filename_prefix=prefix,
                )
                items.append(
                    BulkImageZipItem(
                        filename=name,
                        original=proc_res.original,
                        outputs=proc_res.outputs,
                    )
                )
                total_crops += len(proc_res.outputs)

            return BulkImageZipResponse(
                total_images_processed=len(items),
                total_crops_generated=total_crops,
                items=items,
            )
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP archive file.")
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to process images ZIP: {str(exc)}"
        )
