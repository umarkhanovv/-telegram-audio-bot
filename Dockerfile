# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# System deps: ffmpeg + yt-dlp runtime needs
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp binary (kept up to date independently of pip)
RUN pip install --no-cache-dir yt-dlp && pip uninstall -y aiodns

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy source
COPY . .

# Non-root user for security
RUN useradd -m -u 1000 botuser \
    && mkdir -p /tmp/audio_cache \
    && chown -R botuser:botuser /app /tmp/audio_cache

USER botuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CACHE_DIR=/tmp/audio_cache

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import aiogram; print('ok')" || exit 1

CMD ["python", "main.py"]
