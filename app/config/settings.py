"""
Environment-based configuration using pydantic-settings.
All secrets come from environment variables — never hardcoded.
"""
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ── Core ────────────────────────────────────────────────────────────────
    ENV: str = "production"
    BOT_TOKEN: str

    # ── Spotify ─────────────────────────────────────────────────────────────
    SPOTIFY_CLIENT_ID: str = ""
    SPOTIFY_CLIENT_SECRET: str = ""

    # ── YouTube ─────────────────────────────────────────────────────────────
    YOUTUBE_API_KEY: str = ""

    # ── Storage ─────────────────────────────────────────────────────────────
    CACHE_DIR: Path = Path("/tmp/audio_cache")
    MAX_FILE_SIZE_MB: int = 50

    # ── S3 (optional) ───────────────────────────────────────────────────────
    S3_BUCKET: Optional[str] = None
    S3_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None

    # ── Rate limiting ────────────────────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = 3          # max requests
    RATE_LIMIT_WINDOW_SECONDS: int = 60   # per window (seconds)

    # ── HTTP client ──────────────────────────────────────────────────────────
    HTTP_TIMEOUT_SECONDS: int = 30
    HTTP_MAX_REDIRECTS: int = 3
    HTTP_RETRY_ATTEMPTS: int = 3
    HTTP_RETRY_BACKOFF: float = 1.5

    # ── Audio processing ─────────────────────────────────────────────────────
    AUDIO_BITRATE: str = "320k"
    FFMPEG_PATH: str = "ffmpeg"

    @field_validator("CACHE_DIR", mode="before")
    @classmethod
    def ensure_cache_dir(cls, v: Path) -> Path:
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
