"""
Cache service for processed audio files.
- Local filesystem cache by default (keyed by platform + track ID).
- Optional S3 upload/download when configured.
"""
import hashlib
import logging
from pathlib import Path
from typing import Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


def cache_key(platform: str, track_id: str) -> str:
    """Deterministic cache key."""
    raw = f"{platform}:{track_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def cached_path(platform: str, track_id: str) -> Path:
    return settings.CACHE_DIR / f"{cache_key(platform, track_id)}.mp3"


def is_cached(platform: str, track_id: str) -> bool:
    path = cached_path(platform, track_id)
    return path.exists() and path.stat().st_size > 0


def get_cached(platform: str, track_id: str) -> Optional[Path]:
    path = cached_path(platform, track_id)
    if path.exists() and path.stat().st_size > 0:
        logger.info("Cache hit", extra={"platform": platform, "track_id": track_id})
        return path
    return None


def temp_output_path(platform: str, track_id: str) -> Path:
    """Path for in-progress download (before caching)."""
    key = cache_key(platform, track_id)
    return settings.CACHE_DIR / f"{key}_raw"


async def store_in_cache(source_path: Path, platform: str, track_id: str) -> Path:
    """Move processed file into cache location."""
    dest = cached_path(platform, track_id)
    source_path.rename(dest)
    logger.info(
        "Stored in cache",
        extra={"platform": platform, "track_id": track_id, "size_kb": dest.stat().st_size // 1024},
    )
    # TODO: optionally upload to S3 here
    return dest
