import io
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from creative_pipeline.main import app
from creative_pipeline.models.schemas import VideoAuditResponse


@pytest.fixture
def client():
    return TestClient(app)


def make_test_image_bytes():
    buf = io.BytesIO()
    img = Image.new("RGB", (800, 600), color=(73, 109, 137))
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_root_and_health_endpoints(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["service"] == "Self-Healing Creative Pipeline API"

    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"

    res = client.get("/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_sanitize_text_endpoint(client):
    payload = {
        "creative_type": "HEADLINE",
        "text": "PHOTO EDITOR #1 📸 BEST APP EVER!!!",
    }
    res = client.post("/v1/sanitize/text", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["cleaned_text"] == "Photo Editor 1 Best App Ever"
    assert data["was_modified"] is True
    assert data["char_count"] == 28
    assert data["max_allowed"] == 30
    assert len(data["modifications"]) > 0


def test_sanitize_description_endpoint(client):
    payload = {
        "creative_type": "DESCRIPTION",
        "text": "Fast & Easy photo editing tool at home... Try it today!!!",
    }
    res = client.post("/v1/sanitize/text", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] is True
    assert data["cleaned_text"].count("!") == 1


def test_image_upload_endpoint(client):
    img_bytes = make_test_image_bytes()
    files = {"file": ("test_banner.jpg", img_bytes, "image/jpeg")}
    data = {
        "target_ratios": ["SQUARE", "LANDSCAPE", "PORTRAIT"],
        "portrait_aspect": "4:5",
    }
    res = client.post("/v1/process/image/upload", files=files, data=data)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["status"] == "success"
    assert len(res_data["outputs"]) == 3
    ratios = [o["ratio"] for o in res_data["outputs"]]
    assert "SQUARE" in ratios
    assert "LANDSCAPE" in ratios
    assert "PORTRAIT" in ratios


def test_video_audit_endpoint(client):
    with patch(
        "creative_pipeline.engines.video_auditor.VideoAuditor.audit_video",
        new_callable=AsyncMock,
    ) as mock_audit:
        mock_audit.return_value = VideoAuditResponse(
            video_id="sample12345",
            is_usable=False,
            status="PRIVATE",
            reason="Video is Private. Please change visibility to Unlisted or Public in YouTube Studio.",
            action="DROP_FROM_QUEUE",
        )

        res = client.post(
            "/v1/audit/video",
            json={"video_url": "https://www.youtube.com/watch?v=sample12345"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["video_id"] == "sample12345"
        assert data["is_usable"] is False
        assert data["status"] == "PRIVATE"
        assert data["action"] == "DROP_FROM_QUEUE"


def test_batch_pipeline_endpoint(client):
    with patch(
        "creative_pipeline.engines.image_cropper.ImageCropper.fetch_image_bytes",
        new_callable=AsyncMock,
    ) as mock_img, patch(
        "creative_pipeline.engines.video_auditor.VideoAuditor.audit_video",
        new_callable=AsyncMock,
    ) as mock_vid:
        mock_img.return_value = make_test_image_bytes()
        mock_vid.return_value = VideoAuditResponse(
            video_id="priv_vid_12",
            is_usable=False,
            status="PRIVATE",
            reason="Video is Private",
            action="DROP_FROM_QUEUE",
        )

        payload = {
            "ad_group_alias": "Photo_Editor_US + Android",
            "assets": [
                {"type": "HEADLINE", "content": "EDIT PHOTOS 📸"},
                {"type": "DESCRIPTION", "content": "Fast & Easy photo editing tool at home..."},
                {"type": "IMAGE", "content": "https://drive.google.com/file/d/raw_img/view"},
                {"type": "VIDEO", "content": "https://youtube.com/watch?v=priv_vid_12"},
            ],
        }

        res = client.post("/v1/pipeline/batch", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["ad_group_alias"] == "Photo_Editor_US + Android"
        assert data["metrics"]["submitted"] == 4
        # 1 headline + 1 description + 3 images = 5 ready
        assert data["metrics"]["generated_ready"] == 5
        assert data["metrics"]["dropped"] == 1
        assert len(data["dropped_assets"]) == 1
        assert data["dropped_assets"][0]["type"] == "VIDEO"


def test_pipeline_csv_endpoint(client):
    with patch(
        "creative_pipeline.engines.image_cropper.ImageCropper.fetch_image_bytes",
        new_callable=AsyncMock,
    ) as mock_img:
        mock_img.return_value = make_test_image_bytes()

        csv_content = """ad_group_alias,asset_type,content,orientation
Camp_1,HEADLINE,TOP PHOTO APP 📸,
Camp_1,DESCRIPTION,Edit photos in high quality.,
"""
        files = {"file": ("input.csv", csv_content.encode("utf-8"), "text/csv")}
        res = client.post("/v1/pipeline/csv", files=files)
        assert res.status_code == 200
        assert "text/csv" in res.headers["content-type"]
        assert "READY ASSETS" in res.text
        assert "Top Photo App" in res.text
