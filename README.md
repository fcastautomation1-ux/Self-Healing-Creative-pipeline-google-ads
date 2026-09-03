# 🚀 Self-Healing Creative Pipeline API
### *Autonomous Google Ads Asset Validator, Auto-Corrector, Smart Cropper & Filter Microservice*

---

## 1. Executive Summary & Objective
**Self-Healing Creative Pipeline** is a standalone, high-performance **API-First Microservice** that ingests marketing and creative teams' rough, un-vetted assets (Headlines, Descriptions, Images, YouTube Videos) and exports them **100% policy-compliant, perfectly cropped, and verified** for Google Ads App & Performance Max campaigns.

### Key Value Propositions:
* **Text Auto-Fixing ("Copy Doctor"):** Strips emojis and prohibited symbols, fixes repetitive punctuation, converts ALL-CAPS to Title Case or Sentence Case, and intelligently truncates text at word boundaries to enforce character limits.
* **Smart Image Auto-Cropping ("Visual Engine"):** Auto-crops raw images into Google Ads standard orientations (**1:1 Square, 1.91:1 Landscape, 4:5 / 9:16 Portrait**) with saliency and focal-point detection. Automatically compresses outputs to remain strictly under the 5.0 MB Google Ads cap (< 3.0 MB target).
* **Video Auto-Purge ("Video Cleaner"):** Verifies public accessibility and embed permissions via YouTube Data API v3 (with zero-config oEmbed fallback), dropping private, deleted, or restricted videos before automation blocks.
* **Zero Policy Violations:** Eliminates Google Ads `SYMBOLS`, `CAPITALIZATION`, and `EDITORIAL` rejections.

---

## 2. Architecture & Modules

```
   [ Client Sources ]
   (Next.js CMS Portal / Google Sheet / CLI / Webhook)
                           │
                           ▼ HTTP JSON / Multipart
┌─────────────────────────────────────────────────────────────┐
│          Self-Healing Creative API (FastAPI / Python)       │
├──────────────────────────────┬──────────────────────────────┤
│ 1. Text Transformation Engine│ 2. Smart Visual Engine       │
│    - Regex & Unicode Stripper│    - Saliency / Center Crop  │
│    - Policy Linter & Case Fix│    - Pillow / OpenCV Resizer │
│    - Word-Boundary Shortener │    - WebP/JPEG Compressor    │
├──────────────────────────────┼──────────────────────────────┤
│ 3. Video Health Auditor      │ 4. Storage & Output Adapter  │
│    - YouTube Data API v3     │    - Google Drive / GCS API  │
│    - oEmbed Fallback Checker │    - Google Sheets Exporter  │
└──────────────────────────────┴──────────────────────────────┘
                           │
                           ▼ Clean, Ready-to-Serve Assets
   [ Google Ads API / Production Upload Sheet ]
```

---

## 3. Quickstart & Installation

### Requirements:
- Python 3.11+
- `uv` (recommended) or standard `pip`

### Local Setup:

1. **Clone and setup dependencies:**
   ```bash
   # Using uv (fastest)
   uv sync --extra dev

   # Activate virtual environment
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate
   ```

2. **Configure Environment:**
   ```bash
   cp .env.example .env
   ```
   *(Optional: Add `GOOGLE_SERVICE_ACCOUNT_JSON` for Google Drive uploads or `YOUTUBE_API_KEY` for high-throughput YouTube auditing. Default local storage and oEmbed fallback work out-of-the-box.)*

3. **Start the API Server:**
   ```bash
   uv run uvicorn creative_pipeline.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Interactive Documentation:**
   - Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
   - ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
   - Health Check: [http://localhost:8000/health](http://localhost:8000/health)

---

## 4. API Endpoints Specification

### 1. `POST /v1/sanitize/text`
Sanitizes raw copy according to Google Ads editorial, symbol, and capitalization policies.

* **Request:**
  ```bash
  curl -X POST "http://localhost:8000/v1/sanitize/text" \
    -H "Content-Type: application/json" \
    -d '{
      "creative_type": "HEADLINE",
      "text": "PHOTO EDITOR #1 📸 BEST APP EVER!!!"
    }'
  ```

* **Response:**
  ```json
  {
    "valid": true,
    "original_text": "PHOTO EDITOR #1 📸 BEST APP EVER!!!",
    "cleaned_text": "Photo Editor 1 Best App Ever",
    "was_modified": true,
    "modifications": [
      "Removed prohibited symbols: #",
      "Removed emojis: 📸",
      "Removed exclamation marks (prohibited in headlines)",
      "Converted ALL-CAPS to Title Case"
    ],
    "char_count": 28,
    "max_allowed": 30
  }
  ```

---

### 2. `POST /v1/process/image` (From URL) & `POST /v1/process/image/upload` (Multipart)
Downloads or accepts a raw image, detects focal points using saliency analysis, crops to target Google Ads ratios (1:1 Square, 1.91:1 Landscape, 4:5/9:16 Portrait), compresses, and uploads to storage.

* **Request (JSON URL):**
  ```bash
  curl -X POST "http://localhost:8000/v1/process/image" \
    -H "Content-Type: application/json" \
    -d '{
      "image_url": "https://drive.google.com/file/d/1ABCXYZ/view",
      "target_ratios": ["SQUARE", "LANDSCAPE", "PORTRAIT"],
      "portrait_aspect": "4:5"
    }'
  ```

* **Response:**
  ```json
  {
    "status": "success",
    "original": {
      "dimensions": "1920x1080",
      "size_mb": 2.4,
      "format": "JPEG"
    },
    "outputs": [
      {
        "ratio": "SQUARE",
        "dimensions": "1200x1200",
        "url": "http://localhost:8000/assets/asset_1a2b3c4d_square.jpg",
        "size_mb": 0.85
      },
      {
        "ratio": "LANDSCAPE",
        "dimensions": "1200x628",
        "url": "http://localhost:8000/assets/asset_1a2b3c4d_landscape.jpg",
        "size_mb": 0.58
      },
      {
        "ratio": "PORTRAIT",
        "dimensions": "1200x1500",
        "url": "http://localhost:8000/assets/asset_1a2b3c4d_portrait.jpg",
        "size_mb": 0.92
      }
    ]
  }
  ```

---

### 3. `POST /v1/audit/video`
Audits YouTube video URL for public accessibility and embed permissions.

* **Request:**
  ```bash
  curl -X POST "http://localhost:8000/v1/audit/video" \
    -H "Content-Type: application/json" \
    -d '{
      "video_url": "https://www.youtube.com/watch?v=sample123"
    }'
  ```

* **Response (Private Video):**
  ```json
  {
    "video_id": "sample123",
    "is_usable": false,
    "status": "PRIVATE",
    "reason": "Video is Private. Please change visibility to Unlisted or Public in YouTube Studio.",
    "action": "DROP_FROM_QUEUE"
  }
  ```

---

### 4. `POST /v1/pipeline/batch`
Processes complete multi-asset payloads for an ad group and separates clean ready assets from dropped assets.

* **Request:**
  ```bash
  curl -X POST "http://localhost:8000/v1/pipeline/batch" \
    -H "Content-Type: application/json" \
    -d '{
      "ad_group_alias": "Photo_Editor_US + Android",
      "assets": [
        { "type": "HEADLINE", "content": "EDIT PHOTOS 📸" },
        { "type": "DESCRIPTION", "content": "Fast & Easy photo editing tool at home..." },
        { "type": "IMAGE", "content": "https://drive.google.com/file/d/raw_img/view" },
        { "type": "VIDEO", "content": "https://youtube.com/watch?v=private_vid" }
      ]
    }'
  ```

* **Response:**
  ```json
  {
    "ad_group_alias": "Photo_Editor_US + Android",
    "ready_to_upload": [
      {
        "type": "HEADLINE",
        "content": "Edit Photos",
        "metadata": { "modifications": ["Removed emojis: 📸", "Converted ALL-CAPS to Title Case"], "char_count": 11 }
      },
      {
        "type": "DESCRIPTION",
        "content": "Fast & Easy photo editing tool at home...",
        "metadata": { "modifications": [], "char_count": 40 }
      },
      {
        "type": "IMAGE",
        "content": "http://localhost:8000/assets/asset_sq.jpg",
        "orientation": "SQUARE",
        "metadata": { "dimensions": "1200x1200", "size_mb": 0.82 }
      },
      {
        "type": "IMAGE",
        "content": "http://localhost:8000/assets/asset_ls.jpg",
        "orientation": "LANDSCAPE",
        "metadata": { "dimensions": "1200x628", "size_mb": 0.54 }
      },
      {
        "type": "IMAGE",
        "content": "http://localhost:8000/assets/asset_pr.jpg",
        "orientation": "PORTRAIT",
        "metadata": { "dimensions": "1200x1500", "size_mb": 0.91 }
      }
    ],
    "dropped_assets": [
      {
        "type": "VIDEO",
        "content": "https://youtube.com/watch?v=private_vid",
        "reason": "Video is Private. Please change visibility to Unlisted or Public in YouTube Studio."
      }
    ],
    "metrics": {
      "submitted": 4,
      "generated_ready": 5,
      "dropped": 1
    }
  }
  ```

---

### 5. `POST /v1/pipeline/csv`
Upload a CSV sheet and download an export with production-ready rows and remediation audit report.

```bash
curl -X POST "http://localhost:8000/v1/pipeline/csv" \
  -F "file=@assets_raw.csv" \
  -o cleaned_assets_output.csv
```

---

## 5. Running Automated Tests

Run the full pytest suite (86+ tests covering all edge cases, ratios, and endpoints):
```bash
uv run pytest -v
```

---

## 6. Docker Deployment (Cloud Run / Railway / Render)

Build and run with Docker:
```bash
docker build -t creative-pipeline-api .
docker run -p 8000:8000 --env-file .env creative-pipeline-api
```
