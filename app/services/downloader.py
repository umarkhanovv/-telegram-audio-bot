"""
Downloader service using Cobalt API (cobalt.tools) as primary source.
Cobalt is free, open-source, and handles YouTube reliably from servers.
Falls back to yt-dlp if Cobalt fails.
"""
import asyncio
import logging
import shutil
from pathlib import Path
from typing import Optional

import aiohttp

from app.config.settings import settings
from app.services.models import TrackMetadata

logger = logging.getLogger(__name__)

# Public Cobalt API instances (use multiple for redundancy)
COBALT_INSTANCES = [
    "https://cobalt-api.tnix.dev",
    "https://cobalt.api.lostplaced.com",
    "https://cobalt-api.toffilabs.com",
]


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
    """Try Cobalt first, fall back to yt-dlp."""

    # Try Cobalt API
    try:
        result = await _download_via_cobalt(source_url, output_path)
        if result:
            return result
    except Exception as exc:
        logger.warning("Cobalt failed, trying yt-dlp", extra={"error": str(exc)})

    # Fall back to yt-dlp
    return await _download_via_ytdlp("--cookies", "/app/cookies.txt",source_url, output_path)


async def _download_via_cobalt(source_url: str, output_path: Path) -> Optional[Path]:
    """Download audio via Cobalt API."""
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for instance in COBALT_INSTANCES:
            try:
                # Step 1: Get download URL from Cobalt
                async with session.post(
                    f"{instance}/",
                    json={
                        "url": source_url,
                        "downloadMode": "audio",
                        "audioFormat": "mp3",
                        "audioBitrate": "320",
                    },
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)

                status = data.get("status")

                if status == "error":
                    error = data.get("error", {}).get("code", "unknown")
                    if "private" in error.lower():
                        raise PrivateVideoError("Video is private")
                    continue

                # Get the actual download URL
                download_url = None
                if status in ("stream", "redirect", "tunnel"):
                    download_url = data.get("url")
                elif status == "picker":
                    # Take first audio option
                    items = data.get("picker", [])
                    for item in items:
                        if item.get("type") == "audio":
                            download_url = item.get("url")
                            break
                    if not download_url and items:
                        download_url = items[0].get("url")

                if not download_url:
                    continue

                # Step 2: Download the actual file
                output_file = output_path.with_suffix(".mp3")
                async with session.get(download_url) as dl_resp:
                    if dl_resp.status != 200:
                        continue
                    content = await dl_resp.read()
                    if len(content) < 1024:  # Too small = failed
                        continue
                    output_file.write_bytes(content)
                    logger.info(
                        "Cobalt download success",
                        extra={"instance": instance, "size_kb": len(content) // 1024},
                    )
                    return output_file

            except (PrivateVideoError, GeoBlockedError):
                raise
            except Exception as exc:
                logger.warning(
                    "Cobalt instance failed",
                    extra={"instance": instance, "error": str(exc)},
                )
                continue

    return None


async def _download_via_ytdlp(source_url: str, output_path: Path) -> Path:
    """Download via yt-dlp as fallback."""
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
        "--extractor-args", "youtube:player_client=ios,web",
        source_url,
    ]

    # Use cookies if available
    cookies_path = Path("/app/cookies.txt")
    if cookies_path.exists():
        cmd += ["--cookies", str(cookies_path)]

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

    stem = output_path.stem
    candidates = list(output_path.parent.glob(f"{stem}.*"))
    if not candidates:
        raise DownloadError("yt-dlp completed but no output file found")

    return candidates[0]


async def search_youtube_for_track(metadata: TrackMetadata) -> str:
    """Return a YouTube URL for a Spotify track via yt-dlp search."""
    _check_ytdlp()

    query = f"ytsearch1:{metadata.artist} {metadata.title} audio"
    cmd = [
        "yt-dlp",
        "--print", "webpage_url",
        "--no-playlist",
        "--quiet",
        "--no-check-certificates",
        "--extractor-args", "youtube:player_client=ios,web",
        query,
    ]

    cookies_path = Path("/app/cookies.txt")
    if cookies_path.exists():
        cmd += ["--cookies", str(cookies_path)]

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
        raise DownloadError(
            "YouTube search failed: " + stderr.decode(errors="replace")[:200]
        )

    url = stdout.decode().strip().splitlines()[0]
    if not url.startswith("http"):
        raise DownloadError("No YouTube result found for track")

    logger.info(
        "Resolved Spotify track via YouTube search", extra={"url": url[:80]}
    )
    return url


def _raise_from_ytdlp_error(stderr: str) -> None:
    lower = stderr.lower()
    if "private video" in lower:
        raise PrivateVideoError("This video is private and cannot be downloaded")
    if "geo" in lower or "not available in your country" in lower:
        raise GeoBlockedError("This content is not available in the server region")
    if "too large" in lower:
        raise FileTooLargeError("Source file is too large")
    raise DownloadError("Could not download this track. Please try another link.")


def _check_ytdlp() -> None:
    if not shutil.which("yt-dlp"):
        raise DownloadError("yt-dlp is not installed or not in PATH")
