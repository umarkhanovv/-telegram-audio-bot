"""
URL validation, sanitization, and platform detection.
Defends against SSRF, redirect abuse, and malformed input.
"""
import re
from enum import Enum
from typing import Optional
from urllib.parse import urlparse, parse_qs


class Platform(str, Enum):
    SPOTIFY = "spotify"
    YOUTUBE = "youtube"


# ── Allowlist of trusted hostnames ──────────────────────────────────────────
_SPOTIFY_HOSTS = frozenset({"open.spotify.com"})
_YOUTUBE_HOSTS = frozenset({
    "www.youtube.com",
    "youtube.com",
    "youtu.be",
    "m.youtube.com",
    "music.youtube.com",
})
_ALLOWED_HOSTS = _SPOTIFY_HOSTS | _YOUTUBE_HOSTS

# ── Regex patterns for ID extraction ────────────────────────────────────────
_SPOTIFY_TRACK_RE = re.compile(
    r"open\.spotify\.com/(?:intl-[a-z]{2}/)?track/([A-Za-z0-9]{22})"
)
_YOUTUBE_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})"
)

# ── Private / loopback ranges to block (SSRF) ────────────────────────────────
_PRIVATE_HOST_RE = re.compile(
    r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|::1|0\.0\.0\.0)"
)


class URLValidationError(ValueError):
    pass


def detect_platform(url: str) -> Optional[Platform]:
    """Return the Platform for a URL, or None if unrecognised."""
    parsed = _safe_parse(url)
    if parsed is None:
        return None
    host = parsed.netloc.lower().lstrip("www.")
    if any(h.lstrip("www.") == host for h in _SPOTIFY_HOSTS):
        return Platform.SPOTIFY
    if any(h.lstrip("www.") == host for h in _YOUTUBE_HOSTS):
        return Platform.YOUTUBE
    return None


def validate_url(url: str) -> str:
    """
    Validate and sanitise a URL.
    Returns the cleaned URL or raises URLValidationError.
    """
    if not isinstance(url, str):
        raise URLValidationError("URL must be a string")

    url = url.strip()
    if len(url) > 2048:
        raise URLValidationError("URL too long")

    parsed = _safe_parse(url)
    if parsed is None:
        raise URLValidationError("Malformed URL")

    if parsed.scheme not in ("http", "https"):
        raise URLValidationError("Only http/https URLs are accepted")

    host = parsed.hostname or ""
    if _PRIVATE_HOST_RE.match(host):
        raise URLValidationError("Private/loopback addresses are not allowed")

    if parsed.netloc.lower() not in _ALLOWED_HOSTS:
        raise URLValidationError(
            f"Host '{parsed.netloc}' is not an allowed platform"
        )

    return url


def extract_spotify_track_id(url: str) -> str:
    """Extract a Spotify track ID from a URL."""
    match = _SPOTIFY_TRACK_RE.search(url)
    if not match:
        raise URLValidationError("Could not extract Spotify track ID from URL")
    return match.group(1)


def extract_youtube_video_id(url: str) -> str:
    """Extract a YouTube video ID from a URL (both youtu.be and watch?v=)."""
    # First try query param
    parsed = _safe_parse(url)
    if parsed:
        qs = parse_qs(parsed.query)
        if "v" in qs:
            vid = qs["v"][0]
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                return vid

    match = _YOUTUBE_ID_RE.search(url)
    if not match:
        raise URLValidationError("Could not extract YouTube video ID from URL")
    return match.group(1)


def _safe_parse(url: str):
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return None
        return parsed
    except Exception:
        return None
