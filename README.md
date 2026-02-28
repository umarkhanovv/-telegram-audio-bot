# 🎵 Telegram Audio Bot

A production-ready Telegram bot that accepts Spotify or YouTube track URLs and returns
high-quality MP3 audio files (320kbps, EBU R128 normalized) with embedded metadata.

---

## Features

- **Dual platform** — Spotify tracks (via YouTube fallback) and YouTube videos
- **High-quality audio** — MP3 320kbps, EBU R128 loudness normalization via ffmpeg
- **ID3 metadata** — title, artist, album, and cover art embedded
- **Caching** — processed files cached locally (S3-ready)
- **Rate limiting** — per-user sliding window (3 req / 60s by default)
- **Security** — URL allowlist, SSRF guard, redirect limits, timeouts
- **Structured logging** — JSON lines in production, human-readable in dev
- **Retry logic** — exponential backoff on transient HTTP failures

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| ffmpeg | 6.x+ |
| yt-dlp | latest |
| Docker | 24+ (optional) |

---

## Quick Start

### 1. Clone & configure

```bash
git clone <repo>
cd telegram-audio-bot
cp .env.example .env
# Edit .env with your credentials
```

### 2. Get API credentials

**Telegram Bot Token**
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. `/newbot` → follow prompts → copy token to `BOT_TOKEN`

**Spotify API**
1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create an app → copy `Client ID` and `Client Secret`
3. Set `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`

**YouTube Data API v3**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable "YouTube Data API v3"
3. Create an API key → set `YOUTUBE_API_KEY`

### 3a. Run with Docker (recommended)

```bash
docker compose up --build
```

### 3b. Run locally

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

---

## Configuration Reference

All config via environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `BOT_TOKEN` | — | **Required.** Telegram bot token |
| `SPOTIFY_CLIENT_ID` | — | Spotify app client ID |
| `SPOTIFY_CLIENT_SECRET` | — | Spotify app client secret |
| `YOUTUBE_API_KEY` | — | YouTube Data API v3 key |
| `ENV` | `production` | `development` for pretty logs |
| `CACHE_DIR` | `/tmp/audio_cache` | Local cache directory |
| `MAX_FILE_SIZE_MB` | `50` | Max output file size |
| `RATE_LIMIT_REQUESTS` | `3` | Requests per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window |
| `AUDIO_BITRATE` | `320k` | ffmpeg output bitrate |
| `FFMPEG_PATH` | `ffmpeg` | Path to ffmpeg binary |

---

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

---

## Project Structure

```
.
├── main.py                     # Entrypoint — bot startup
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── app/
    ├── config/
    │   └── settings.py         # Pydantic-settings env config
    ├── handlers/
    │   └── audio.py            # aiogram message handlers
    ├── services/
    │   ├── models.py           # TrackMetadata dataclass
    │   ├── orchestrator.py     # Pipeline coordinator
    │   ├── spotify.py          # Spotify Web API client
    │   ├── youtube.py          # YouTube Data API client
    │   ├── downloader.py       # yt-dlp wrapper
    │   ├── audio_processor.py  # ffmpeg conversion + normalization
    │   └── cache.py            # Local/S3 cache
    └── utils/
        ├── url_parser.py       # URL validation, SSRF guard
        ├── rate_limiter.py     # Sliding window rate limiter
        ├── http_client.py      # aiohttp + retry logic
        └── logging.py          # Structured JSON logging
```

---

## Architecture Decisions

### Why yt-dlp for Spotify?
Spotify's Web API provides metadata but no audio streams (those are DRM-protected).
The standard open-source approach is to search YouTube for `"<artist> <title>"` using
yt-dlp's built-in `ytsearch:` feature. This is how most CLI music tools work.

### Why in-process asyncio queue (no Redis)?
For a single-instance bot, `asyncio.create_subprocess_exec` for ffmpeg/yt-dlp achieves
true parallelism without the operational overhead of Redis + RQ. Adding Redis is
straightforward if horizontal scaling is needed.

### Why two-stage Docker build?
Keeps the runtime image lean by only copying installed packages from the builder.
The final image contains only `python:3.11-slim` + `ffmpeg` + runtime packages.

### Why aiohttp over httpx?
aiohttp has first-class aiogram integration, a mature connector pool, and full
async streaming support — all needed for cover art downloads and API calls.

### Cache keying
Cache keys are `sha256(platform:track_id)` — deterministic, collision-resistant,
filesystem-safe, and safe to store in S3 without encoding.

### Rate limiting
Sliding window (not token bucket) because it gives a fairer per-user experience:
it naturally allows bursts up to the window limit without permanently penalising
users who occasionally batch requests.

---

## Security Notes

- **SSRF**: `validate_url()` enforces an allowlist of hostnames (`open.spotify.com`,
  `youtube.com`, `youtu.be`). Private/loopback IPs are blocked. Redirects to private
  hosts are also blocked via aiohttp trace hooks.
- **Input sanitisation**: URL length is capped at 2048 chars. Track IDs are validated
  against strict regex before use as API parameters.
- **Redirect limit**: `HTTP_MAX_REDIRECTS=3` prevents redirect chain abuse.
- **Timeouts**: Every HTTP call has a `HTTP_TIMEOUT_SECONDS` total timeout.
- **Non-root container**: The Docker image runs as `botuser` (UID 1000).
