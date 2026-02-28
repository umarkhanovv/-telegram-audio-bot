"""
Orchestrator — high-level pipeline:
  URL → metadata → download → process → cache → return Path
"""
import logging
import tempfile
from pathlib import Path
from typing import Optional

import aiohttp

from app.services import cache, downloader, audio_processor
from app.services.models import TrackMetadata
from app.services.spotify import SpotifyService
from app.services.youtube import YouTubeService
from app.utils.url_parser import (
    Platform,
    extract_spotify_track_id,
    extract_youtube_video_id,
)

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        self._spotify = SpotifyService(session)
        self._youtube = YouTubeService(session)

    async def process_url(self, url: str, platform: Platform) -> tuple[Path, TrackMetadata]:
        """
        Full pipeline. Returns (audio_path, metadata).
        Raises descriptive exceptions on failure.
        """
        if platform == Platform.SPOTIFY:
            return await self._process_spotify(url)
        else:
            return await self._process_youtube(url)

    async def _process_spotify(self, url: str) -> tuple[Path, TrackMetadata]:
        track_id = extract_spotify_track_id(url)

        # Check cache first
        cached = cache.get_cached(Platform.SPOTIFY, track_id)
        if cached:
            # Still need metadata for bot caption — re-fetch or read ID3
            # For simplicity, fetch metadata regardless (it's fast)
            pass

        metadata = await self._spotify.get_track_metadata(track_id)
        logger.info("Spotify metadata", extra={"track": metadata.display_name})

        if cached:
            return cached, metadata

        # Resolve to YouTube for actual audio
        yt_url = await downloader.search_youtube_for_track(metadata)
        return await self._download_and_process(yt_url, Platform.SPOTIFY, track_id, metadata)

    async def _process_youtube(self, url: str) -> tuple[Path, TrackMetadata]:
        video_id = extract_youtube_video_id(url)

        cached = cache.get_cached(Platform.YOUTUBE, video_id)
        metadata = await self._youtube.get_video_metadata(video_id)
        logger.info("YouTube metadata", extra={"track": metadata.display_name})

        if cached:
            return cached, metadata

        return await self._download_and_process(url, Platform.YOUTUBE, video_id, metadata)

    async def _download_and_process(
        self,
        source_url: str,
        platform: Platform,
        track_id: str,
        metadata: TrackMetadata,
    ) -> tuple[Path, TrackMetadata]:
        raw_dir = Path(tempfile.mkdtemp(prefix="bot_dl_"))
        raw_output = raw_dir / "raw_audio"
        mp3_output = raw_dir / "output.mp3"

        try:
            raw_path = await downloader.download_audio(source_url, raw_output, metadata)
            await audio_processor.process_audio(raw_path, mp3_output, metadata, self._session)

            # Move to cache
            final_path = await cache.store_in_cache(mp3_output, platform, track_id)
        finally:
            # Cleanup temp files (not the cached final)
            for f in raw_dir.iterdir():
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass
            try:
                raw_dir.rmdir()
            except Exception:
                pass

        return final_path, metadata
