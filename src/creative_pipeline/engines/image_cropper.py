import io
import logging
import re
import uuid
from typing import List, Optional, Tuple

import cv2
import httpx
import numpy as np
from PIL import Image

from creative_pipeline.config import settings
from creative_pipeline.models.schemas import (
    ImageProcessRequest,
    ImageProcessResponse,
    OriginalImageMeta,
    ProcessedImageOutput,
    TargetRatio,
)
from creative_pipeline.storage.base import BaseStorage
from creative_pipeline.storage import get_storage

logger = logging.getLogger(__name__)


class ImageCropper:
    """Module 2: Smart Image Auto-Cropper & Resizer ('Visual Engine')."""

    # Target orientations and recommended dimensions
    SPECS = {
        TargetRatio.SQUARE: {
            "ratio": 1.0,
            "target_dim": (1200, 1200),
            "min_dim": (300, 300),
        },
        TargetRatio.LANDSCAPE: {
            "ratio": 1200 / 628,  # ~1.91:1
            "target_dim": (1200, 628),
            "min_dim": (600, 314),
        },
        TargetRatio.PORTRAIT: {
            "4:5": {
                "ratio": 4 / 5,  # 0.8
                "target_dim": (1200, 1500),
                "min_dim": (480, 600),
            },
            "9:16": {
                "ratio": 9 / 16,  # 0.5625
                "target_dim": (1080, 1920),
                "min_dim": (600, 1067),
            },
        },
    }

    def __init__(self, storage: Optional[BaseStorage] = None):
        self.storage = storage or get_storage()

    async def fetch_image_bytes(self, url: str) -> bytes:
        """Downloads image bytes from web or Google Drive URL."""
        download_url = self._normalize_drive_url(url)
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(download_url)
            resp.raise_for_status()
            return resp.content

    def _normalize_drive_url(self, url: str) -> str:
        """Converts Google Drive view URL to direct export download URL."""
        if "drive.google.com" in url:
            # Match /file/d/{FILE_ID} or ?id={FILE_ID}
            match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
            if match:
                file_id = match.group(1)
                return f"https://drive.google.com/uc?export=download&id={file_id}"
            match_param = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
            if match_param:
                file_id = match_param.group(1)
                return f"https://drive.google.com/uc?export=download&id={file_id}"
        return url

    async def process_image(
        self,
        image_bytes: bytes,
        target_ratios: List[TargetRatio],
        destination_folder_id: Optional[str] = None,
        portrait_aspect: str = "4:5",
        filename_prefix: Optional[str] = None,
    ) -> ImageProcessResponse:
        """Processes raw image bytes into compliant cropped Google Ads assets."""
        original_size_mb = round(len(image_bytes) / (1024 * 1024), 2)
        
        with Image.open(io.BytesIO(image_bytes)) as pil_img:
            # Handle orientation from EXIF if present
            pil_img = self._auto_orient(pil_img)
            orig_w, orig_h = pil_img.size
            orig_fmt = pil_img.format or "JPEG"
            original_meta = OriginalImageMeta(
                dimensions=f"{orig_w}x{orig_h}",
                size_mb=original_size_mb,
                format=orig_fmt,
            )

            outputs: List[ProcessedImageOutput] = []
            prefix = filename_prefix or f"asset_{uuid.uuid4().hex[:8]}"

            for ratio_enum in target_ratios:
                cropped_img, target_w, target_h = self._smart_crop_and_resize(
                    pil_img, ratio_enum, portrait_aspect
                )

                # Compress and encode to bytes
                output_bytes, fmt, ext = self._compress_image(cropped_img)
                output_size_mb = round(len(output_bytes) / (1024 * 1024), 2)

                ratio_label = ratio_enum.value.lower()
                filename = f"{prefix}_{ratio_label}.{ext}"
                content_type = f"image/{fmt.lower()}"

                url = await self.storage.save(
                    data=output_bytes,
                    filename=filename,
                    content_type=content_type,
                    folder_id=destination_folder_id,
                )

                outputs.append(
                    ProcessedImageOutput(
                        ratio=ratio_enum.value,
                        dimensions=f"{target_w}x{target_h}",
                        url=url,
                        size_mb=output_size_mb,
                    )
                )

            return ImageProcessResponse(
                status="success",
                original=original_meta,
                outputs=outputs,
            )

    def _auto_orient(self, img: Image.Image) -> Image.Image:
        """Corrects orientation based on EXIF orientation tag."""
        try:
            from PIL import ImageOps
            return ImageOps.exif_transpose(img) or img
        except Exception:
            return img

    def _smart_crop_and_resize(
        self,
        img: Image.Image,
        ratio_enum: TargetRatio,
        portrait_aspect: str = "4:5",
    ) -> Tuple[Image.Image, int, int]:
        """Calculates optimal crop box using saliency / gradient energy and resizes."""
        if ratio_enum == TargetRatio.PORTRAIT:
            spec = self.SPECS[TargetRatio.PORTRAIT].get(
                portrait_aspect, self.SPECS[TargetRatio.PORTRAIT]["4:5"]
            )
        else:
            spec = self.SPECS[ratio_enum]

        target_ratio = spec["ratio"]
        target_w, target_h = spec["target_dim"]

        orig_w, orig_h = img.size
        current_ratio = orig_w / orig_h

        # Determine crop dimensions in original image coordinates
        if current_ratio > target_ratio:
            # Source is wider than target ratio -> crop width
            crop_h = orig_h
            crop_w = int(round(orig_h * target_ratio))
            # Find best horizontal offset (x)
            crop_x = self._find_best_offset_axis(img, orig_w, crop_w, axis="x")
            crop_y = 0
        else:
            # Source is taller than target ratio -> crop height
            crop_w = orig_w
            crop_h = int(round(orig_w / target_ratio))
            # Find best vertical offset (y)
            crop_y = self._find_best_offset_axis(img, orig_h, crop_h, axis="y")
            crop_x = 0

        # Safety clamp
        crop_x = max(0, min(crop_x, orig_w - crop_w))
        crop_y = max(0, min(crop_y, orig_h - crop_h))

        cropped = img.crop((crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))

        # Resize to target Google Ads dimensions using Lanczos
        # If original crop is larger than target, downscale; if smaller, scale up
        resized = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
        return resized, target_w, target_h

    def _find_best_offset_axis(
        self, img: Image.Image, full_len: int, crop_len: int, axis: str = "x"
    ) -> int:
        """Finds the optimal crop offset along an axis using gradient energy/saliency."""
        slide_range = full_len - crop_len
        if slide_range <= 0:
            return 0

        # Fast saliency: downsample thumbnail for gradient energy map
        thumb_size = 256
        scale = thumb_size / max(img.size)
        t_w = max(1, int(img.width * scale))
        t_h = max(1, int(img.height * scale))

        thumb = img.resize((t_w, t_h), Image.Resampling.BILINEAR).convert("L")
        arr = np.array(thumb, dtype=np.float32)

        # Compute gradient magnitude (Sobel)
        gx = cv2.Sobel(arr, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(arr, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = cv2.magnitude(gx, gy)

        if axis == "x":
            # Profile of energy along X
            profile = np.sum(grad_mag, axis=0)  # shape (t_w,)
            scaled_crop_len = int(round(crop_len * scale))
            scaled_full_len = t_w
        else:
            # Profile of energy along Y
            profile = np.sum(grad_mag, axis=1)  # shape (t_h,)
            scaled_crop_len = int(round(crop_len * scale))
            scaled_full_len = t_h

        # Default center offset
        center_offset = slide_range // 2

        if scaled_crop_len >= scaled_full_len or len(profile) == 0:
            return center_offset

        # Sliding window sum over profile to find window with max energy
        max_energy = -1.0
        best_scaled_idx = 0
        window_size = max(1, scaled_crop_len)

        # Cumulative sum for fast window range query
        cumsum = np.insert(np.cumsum(profile), 0, 0)
        max_idx = scaled_full_len - window_size
        if max_idx <= 0:
            return center_offset

        for i in range(max_idx + 1):
            energy = cumsum[i + window_size] - cumsum[i]
            if energy > max_energy:
                max_energy = energy
                best_scaled_idx = i

        # Convert scaled index back to original image space
        calculated_offset = int(round(best_scaled_idx / scale))
        return max(0, min(calculated_offset, slide_range))

    def _compress_image(
        self, img: Image.Image, target_bytes: int = settings.IMAGE_TARGET_COMPRESSION_BYTES
    ) -> Tuple[bytes, str, str]:
        """Compresses image to ensure it is under the Google Ads 5.0 MB cap."""
        # Convert RGBA to RGB for JPEG if no transparency
        if img.mode in ("RGBA", "LA", "P"):
            # Check if there is actual transparency
            if img.mode == "RGBA" and self._has_transparency(img):
                fmt = "PNG"
                ext = "png"
                buf = io.BytesIO()
                img.save(buf, format=fmt, optimize=True)
                data = buf.getvalue()
                if len(data) <= settings.IMAGE_MAX_SIZE_BYTES:
                    return data, fmt, ext
            # Otherwise convert to RGB
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                rgb_img.paste(img, mask=img.split()[3])
            else:
                rgb_img.paste(img)
            img = rgb_img
        elif img.mode != "RGB":
            img = img.convert("RGB")

        fmt = "JPEG"
        ext = "jpg"

        # Quality ladder: 92 -> 85 -> 75 -> 65 -> 50
        qualities = [92, 85, 75, 65, 50]
        data = b""
        for q in qualities:
            buf = io.BytesIO()
            img.save(buf, format=fmt, quality=q, optimize=True)
            data = buf.getvalue()
            if len(data) <= target_bytes:
                return data, fmt, ext

        return data, fmt, ext

    def _has_transparency(self, img: Image.Image) -> bool:
        """Checks if RGBA image has non-opaque pixels."""
        if img.mode != "RGBA":
            return False
        alpha = img.split()[3]
        min_val, _ = alpha.getextrema()
        return min_val < 255
