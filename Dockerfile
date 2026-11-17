# Multi-stage production Dockerfile for AI Clipper Platform
FROM python:3.12-slim-bookworm AS base

# Install essential system dependencies and FFmpeg with libass support
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libass9 \
    libass-dev \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install via pip
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Create non-root system user and group
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/bash -m appuser

# Copy backend and frontend code
COPY backend /app/backend
COPY frontend /app/frontend

# Create persistent storage volumes and configure permissions
RUN mkdir -p /app/backend/storage/downloads \
    /app/backend/storage/clips \
    /app/backend/storage/subtitles \
    /app/backend/storage/thumbnails \
    && chown -R appuser:appgroup /app

USER appuser

WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV ENVIRONMENT=production
ENV REQUIRE_ADMIN_KEY=true

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD-SHELL curl -fsS "http://localhost:${PORT:-8080}/api/health" || exit 1

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
