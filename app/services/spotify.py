"""
Spotify service.
- OAuth2 client-credentials token management (auto-refresh).
- Track metadata fetching via Spotify Web API.
- NOTE: Spotify does not provide downloadable audio. We resolve playback
  via yt-dlp by searching YouTube for "<artist> <title>" — a common
  open-source approach used in CLI tools.
"""
import logging
import time
from typing import Optional

import aiohttp

from app.config.settings import settings
from app.services.models import TrackMetadata
from app.utils.http_client import HttpError, fetch_json

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE = "https://api.spotify.com/v1"


class SpotifyService:
    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    async def get_track_metadata(self, track_id: str) -> TrackMetadata:
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        data = await fetch_json(
            self._session,
            f"{_API_BASE}/tracks/{track_id}",
            headers=headers,
        )
        return _parse_track(data)

    async def _get_token(self) -> str:
        now = time.monotonic()
        if self._token and now < self._token_expires_at - 30:
            return self._token

        if not settings.SPOTIFY_CLIENT_ID or not settings.SPOTIFY_CLIENT_SECRET:
            raise RuntimeError(
                "Spotify credentials not configured. "
                "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET."
            )

        auth = aiohttp.BasicAuth(
            settings.SPOTIFY_CLIENT_ID,
            settings.SPOTIFY_CLIENT_SECRET,
        )
        async with self._session.post(
            _TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=auth,
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise HttpError(resp.status, f"Spotify auth failed: {body[:200]}")
            payload = await resp.json()

        self._token = payload["access_token"]
        self._token_expires_at = now + payload.get("expires_in", 3600)
        logger.info("Spotify token refreshed")
        return self._token


def _parse_track(data: dict) -> TrackMetadata:
    artists = ", ".join(a["name"] for a in data.get("artists", []))
    images = data.get("album", {}).get("images", [])
    cover_url = images[0]["url"] if images else None
    return TrackMetadata(
        title=data["name"],
        artist=artists,
        duration_ms=data["duration_ms"],
        cover_url=cover_url,
        album=data.get("album", {}).get("name"),
        platform_id=data["id"],
    )
