# Multi-stage Dockerfile for Self-Healing Creative Pipeline API
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project specification files
COPY pyproject.toml README.md ./

# Install dependencies into virtualenv
RUN uv venv /app/.venv && \
    uv pip install --no-cache -r pyproject.toml

# Final runtime stage
FROM python:3.11-slim AS runner

WORKDIR /app

# Install runtime system libraries for OpenCV & imaging
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment and source code
COPY --from=builder /app/.venv /app/.venv
COPY src/ /app/src/
COPY README.md /app/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV HOST="0.0.0.0"
ENV PORT="8000"

EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "creative_pipeline.main:app", "--host", "0.0.0.0", "--port", "8000"]
