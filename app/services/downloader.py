"""
Downloader service — wraps yt-dlp to extract audio.
Works for both YouTube URLs and Spotify (via YouTube search fallback).
"""
import asyncio
import logging
import shutil
from pathlib import Path
from typing import Optional

from app.config.settings import settings
from app.services.models import TrackMetadata

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    pass


class FileTooLargeError(DownloadError):
    pass


class GeoBlockedError(DownloadError):
    pass


class PrivateVideoError(DownloadError):
    pass


async def download_audio(
    source_url: str,
    output_path: Path,
    metadata: Optional[TrackMetadata] = None,
) -> Path:
    """
    Download best-quality audio from source_url using yt-dlp.
    Returns path to the downloaded raw audio file (pre-ffmpeg).
    """
    _check_ytdlp()

    raw_output = output_path.with_suffix(".%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--format", "bestaudio/best",
        "--no-check-certificates",
        "--geo-bypass",
        "--socket-timeout", "30",
        "--retries", "3",
        "--output", str(raw_output),
        "--no-progress",
        "--quiet",
        source_url,
        "--extractor-args", "youtube:player_client=web",
        "--no-check-certificates",
    ]

    logger.info("Starting yt-dlp download", extra={"url": source_url[:80]})

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=settings.HTTP_TIMEOUT_SECONDS * 4,
        )
    except asyncio.TimeoutError as exc:
        raise DownloadError("Download timed out") from exc

    if proc.returncode != 0:
        err = stderr.decode(errors="replace")
        _raise_from_ytdlp_error(err)

    # Find the actual downloaded file (yt-dlp fills in extension)
    stem = output_path.stem
    candidates = list(output_path.parent.glob(f"{stem}.*"))
    if not candidates:
        raise DownloadError("yt-dlp completed but no output file found")

    return candidates[0]


async def search_youtube_for_track(metadata: TrackMetadata) -> str:
    """Return a YouTube URL for a Spotify track via yt-dlp search."""
    query = f"ytsearch1:{metadata.artist} {metadata.title} audio"
    cmd = [
        "yt-dlp",
        "--print", "webpage_url",
        "--no-playlist",
        "--quiet",
        query,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError as exc:
        raise DownloadError("YouTube search timed out") from exc

    if proc.returncode != 0:
        raise DownloadError("YouTube search failed: " + stderr.decode(errors="replace")[:200])

    url = stdout.decode().strip().splitlines()[0]
    if not url.startswith("http"):
        raise DownloadError("No YouTube result found for track")

    logger.info("Resolved Spotify track via YouTube search", extra={"url": url[:80]})
    return url


def _raise_from_ytdlp_error(stderr: str) -> None:
    lower = stderr.lower()
    if "private video" in lower or "private" in lower:
        raise PrivateVideoError("This video is private and cannot be downloaded")
    if "geo" in lower or "not available in your country" in lower:
        raise GeoBlockedError("This content is geo-blocked in the server's region")
    if "too large" in lower or "file is too large" in lower:
        raise FileTooLargeError("Source file is too large")
    raise DownloadError(f"yt-dlp error: {stderr[:300]}")


def _check_ytdlp() -> None:
    if not shutil.which("yt-dlp"):
        raise DownloadError("yt-dlp is not installed or not in PATH")
