"""
YouTube service.
- Metadata via YouTube Data API v3.
- Audio extraction via yt-dlp (subprocess, async wrapper).
"""
import asyncio
import logging
from typing import Optional

import aiohttp

from app.config.settings import settings
from app.services.models import TrackMetadata
from app.utils.http_client import fetch_json

logger = logging.getLogger(__name__)

_YT_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeService:
    def __init__(self, session: aiohttp.ClientSession):
        self._session = session

    async def get_video_metadata(self, video_id: str) -> TrackMetadata:
        if not settings.YOUTUBE_API_KEY:
            raise RuntimeError("YOUTUBE_API_KEY not configured")

        data = await fetch_json(
            self._session,
            f"{_YT_API_BASE}/videos",
            params={
                "id": video_id,
                "part": "snippet,contentDetails",
                "key": settings.YOUTUBE_API_KEY,
            },
        )
        items = data.get("items", [])
        if not items:
            raise ValueError(f"YouTube video not found: {video_id}")

        return _parse_video(items[0], video_id)


def _parse_video(item: dict, video_id: str) -> TrackMetadata:
    snippet = item.get("snippet", {})
    thumbnails = snippet.get("thumbnails", {})
    cover_url = (
        thumbnails.get("maxres", thumbnails.get("high", thumbnails.get("default", {})))
        .get("url")
    )
    # Parse ISO 8601 duration → ms
    duration_str = item.get("contentDetails", {}).get("duration", "PT0S")
    duration_ms = _iso_duration_to_ms(duration_str)

    title = snippet.get("title", "Unknown Title")
    channel = snippet.get("channelTitle", "Unknown Artist")

    return TrackMetadata(
        title=title,
        artist=channel,
        duration_ms=duration_ms,
        cover_url=cover_url,
        platform_id=video_id,
    )


def _iso_duration_to_ms(duration: str) -> int:
    """Parse ISO 8601 duration string to milliseconds."""
    import re
    pattern = re.compile(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", re.IGNORECASE
    )
    match = pattern.match(duration)
    if not match:
        return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return (h * 3600 + m * 60 + s) * 1000
