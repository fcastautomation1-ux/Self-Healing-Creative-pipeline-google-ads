import io
import pytest
from PIL import Image, ImageDraw

from creative_pipeline.engines.image_cropper import ImageCropper
from creative_pipeline.models.schemas import TargetRatio
from creative_pipeline.storage.local import LocalStorage


@pytest.fixture
def temp_storage(tmp_path):
    return LocalStorage(storage_dir=str(tmp_path), base_url="http://testserver")


@pytest.fixture
def cropper(temp_storage):
    return ImageCropper(storage=temp_storage)


def create_test_image_bytes(
    width: int, height: int, pattern: str = "plain", color=(100, 150, 200)
) -> bytes:
    """Helper to generate in-memory synthetic images for testing."""
    img = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(img)

    if pattern == "left_focal":
        # Draw high-contrast shapes on the left side
        draw.rectangle([10, 10, width // 4, height - 10], fill=(255, 0, 0))
        draw.ellipse([20, 20, width // 4 - 10, height // 2], fill=(255, 255, 0))
    elif pattern == "right_focal":
        # Draw high-contrast shapes on the right side
        draw.rectangle([width - width // 4, 10, width - 10, height - 10], fill=(255, 0, 0))
        draw.ellipse([width - width // 4 + 10, 20, width - 20, height // 2], fill=(255, 255, 0))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


class TestImageCropperDimensions:
    @pytest.mark.asyncio
    async def test_square_crop_dimensions(self, cropper):
        # 1920x1080 Landscape input
        img_bytes = create_test_image_bytes(1920, 1080)
        res = await cropper.process_image(
            image_bytes=img_bytes,
            target_ratios=[TargetRatio.SQUARE],
        )
        assert res.status == "success"
        assert len(res.outputs) == 1
        out = res.outputs[0]
        assert out.ratio == "SQUARE"
        assert out.dimensions == "1200x1200"
        assert out.url.startswith("http://testserver/assets/")
        assert out.size_mb > 0
        assert out.size_mb < 5.0

    @pytest.mark.asyncio
    async def test_landscape_crop_dimensions(self, cropper):
        # 1080x1080 Square input -> 1200x628 Landscape
        img_bytes = create_test_image_bytes(1080, 1080)
        res = await cropper.process_image(
            image_bytes=img_bytes,
            target_ratios=[TargetRatio.LANDSCAPE],
        )
        assert res.status == "success"
        assert len(res.outputs) == 1
        out = res.outputs[0]
        assert out.ratio == "LANDSCAPE"
        assert out.dimensions == "1200x628"

    @pytest.mark.asyncio
    async def test_portrait_4_5_dimensions(self, cropper):
        img_bytes = create_test_image_bytes(1920, 1080)
        res = await cropper.process_image(
            image_bytes=img_bytes,
            target_ratios=[TargetRatio.PORTRAIT],
            portrait_aspect="4:5",
        )
        assert res.status == "success"
        out = res.outputs[0]
        assert out.ratio == "PORTRAIT"
        assert out.dimensions == "1200x1500"

    @pytest.mark.asyncio
    async def test_portrait_9_16_dimensions(self, cropper):
        img_bytes = create_test_image_bytes(1920, 1080)
        res = await cropper.process_image(
            image_bytes=img_bytes,
            target_ratios=[TargetRatio.PORTRAIT],
            portrait_aspect="9:16",
        )
        assert res.status == "success"
        out = res.outputs[0]
        assert out.ratio == "PORTRAIT"
        assert out.dimensions == "1080x1920"

    @pytest.mark.asyncio
    async def test_all_target_ratios_together(self, cropper):
        img_bytes = create_test_image_bytes(2000, 1500)
        res = await cropper.process_image(
            image_bytes=img_bytes,
            target_ratios=[TargetRatio.SQUARE, TargetRatio.LANDSCAPE, TargetRatio.PORTRAIT],
        )
        assert res.status == "success"
        assert len(res.outputs) == 3
        ratios = {o.ratio for o in res.outputs}
        assert ratios == {"SQUARE", "LANDSCAPE", "PORTRAIT"}


class TestSmartSaliencyCropping:
    def test_saliency_biases_toward_left_content(self, cropper):
        # 1600x800 image with strong content on left
        img_bytes = create_test_image_bytes(1600, 800, pattern="left_focal")
        img = Image.open(io.BytesIO(img_bytes))
        # Crop to square 800x800: sliding range is 1600 - 800 = 800
        offset = cropper._find_best_offset_axis(img, 1600, 800, axis="x")
        # Since focal element is in [10, 400], offset should be close to 0 (left)
        assert offset < 400

    def test_saliency_biases_toward_right_content(self, cropper):
        # 1600x800 image with strong content on right
        img_bytes = create_test_image_bytes(1600, 800, pattern="right_focal")
        img = Image.open(io.BytesIO(img_bytes))
        offset = cropper._find_best_offset_axis(img, 1600, 800, axis="x")
        # Since focal element is in [1200, 1600], offset should be shifted to right
        assert offset > 400


class TestDriveUrlNormalization:
    def test_view_url_conversion(self, cropper):
        url = "https://drive.google.com/file/d/1ABC123XYZ/view?usp=sharing"
        normalized = cropper._normalize_drive_url(url)
        assert normalized == "https://drive.google.com/uc?export=download&id=1ABC123XYZ"

    def test_open_id_conversion(self, cropper):
        url = "https://drive.google.com/open?id=FILE999"
        normalized = cropper._normalize_drive_url(url)
        assert normalized == "https://drive.google.com/uc?export=download&id=FILE999"

    def test_standard_url_untouched(self, cropper):
        url = "https://example.com/images/banner.jpg"
        assert cropper._normalize_drive_url(url) == url
