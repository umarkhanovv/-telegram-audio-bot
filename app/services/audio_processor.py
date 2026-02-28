"""
Audio processor.
- Converts any format → MP3 320kbps via ffmpeg.
- EBU R128 loudness normalization (two-pass).
- Embeds ID3 metadata: title, artist, album, cover art.
- Enforces 50 MB file size limit.
"""
import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import aiohttp

from app.config.settings import settings
from app.services.models import TrackMetadata

logger = logging.getLogger(__name__)


class AudioProcessingError(Exception):
    pass


class FileTooLargeError(AudioProcessingError):
    pass


async def process_audio(
    input_path: Path,
    output_path: Path,
    metadata: TrackMetadata,
    session: Optional[aiohttp.ClientSession] = None,
) -> Path:
    """
    Full pipeline: convert → normalize → embed metadata → validate size.
    Returns output_path.
    """
    _check_ffmpeg()

    cover_path: Optional[Path] = None
    if metadata.cover_url and session:
        cover_path = await _download_cover(session, metadata.cover_url, output_path.parent)

    try:
        # Two-pass EBU R128 normalization then encode to MP3 320k
        await _ffmpeg_encode(input_path, output_path, metadata, cover_path)
    finally:
        if cover_path and cover_path.exists():
            cover_path.unlink(missing_ok=True)

    _check_file_size(output_path)
    return output_path


async def _ffmpeg_encode(
    input_path: Path,
    output_path: Path,
    metadata: TrackMetadata,
    cover_path: Optional[Path],
) -> None:
    """Single-pass encode with loudnorm filter and ID3 tags."""
    cmd = [
        settings.FFMPEG_PATH,
        "-y",                          # overwrite
        "-i", str(input_path),
        # Cover art input (optional)
        *(["-i", str(cover_path)] if cover_path else []),
        # Audio filters: loudness normalisation (EBU R128 integrated target -14 LUFS)
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:a", "libmp3lame",
        "-b:a", settings.AUDIO_BITRATE,
        "-id3v2_version", "3",
        # Map cover art if present
        *(["-map", "0:a", "-map", "1:v", "-c:v", "mjpeg",
           "-metadata:s:v", "comment=Cover (front)"] if cover_path else []),
        # ID3 tags
        "-metadata", f"title={_safe_meta(metadata.title)}",
        "-metadata", f"artist={_safe_meta(metadata.artist)}",
        *(["-metadata", f"album={_safe_meta(metadata.album)}"] if metadata.album else []),
        "-loglevel", "error",
        str(output_path),
    ]

    logger.info("Running ffmpeg", extra={"output": str(output_path)})
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    except asyncio.TimeoutError as exc:
        proc.kill()
        raise AudioProcessingError("ffmpeg timed out after 300s") from exc

    if proc.returncode != 0:
        err = stderr.decode(errors="replace")
        raise AudioProcessingError(f"ffmpeg failed: {err[:400]}")


async def _download_cover(
    session: aiohttp.ClientSession,
    url: str,
    dest_dir: Path,
) -> Optional[Path]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                cover_path = dest_dir / "cover.jpg"
                content = await resp.read()
                cover_path.write_bytes(content)
                return cover_path
    except Exception as exc:
        logger.warning("Failed to download cover art", extra={"error": str(exc)})
    return None


def _check_file_size(path: Path) -> None:
    size = path.stat().st_size
    if size > settings.max_file_size_bytes:
        path.unlink(missing_ok=True)
        raise FileTooLargeError(
            f"Processed file is {size / 1024 / 1024:.1f}MB, "
            f"exceeds {settings.MAX_FILE_SIZE_MB}MB limit"
        )


def _safe_meta(value: str) -> str:
    """Escape ffmpeg metadata value."""
    return value.replace("=", "\\=").replace(";", "\\;").replace("#", "\\#")


def _check_ffmpeg() -> None:
    if not shutil.which(settings.FFMPEG_PATH):
        raise AudioProcessingError(
            f"ffmpeg not found at '{settings.FFMPEG_PATH}'. "
            "Ensure ffmpeg is installed and in PATH."
        )
