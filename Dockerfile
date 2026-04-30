# Production Dockerfile for DocsQA API and Background Ingestion Worker
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# Install uv, then dependencies pinned by uv.lock (no drift from what CI tested)
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code (.venv is excluded by .dockerignore)
COPY . .

EXPOSE 8000

# Default command runs FastAPI via Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
