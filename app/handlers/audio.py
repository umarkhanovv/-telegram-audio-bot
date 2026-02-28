"""
Telegram message handlers.
- /start  → welcome message
- Any text message → try to process as URL
"""
import logging
from pathlib import Path

import aiohttp
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile, BufferedInputFile

from app.services.downloader import DownloadError, GeoBlockedError, PrivateVideoError
from app.services.audio_processor import FileTooLargeError, AudioProcessingError
from app.services.orchestrator import Orchestrator
from app.utils.url_parser import (
    detect_platform,
    validate_url,
    URLValidationError,
)
from app.utils.rate_limiter import rate_limiter, RateLimitExceeded
from app.utils.http_client import build_session

logger = logging.getLogger(__name__)
router = Router()

_WELCOME = (
    "그녀의 눈은 밤하늘보다 깊었고,\n"
    "그 미소는 새벽보다 찬란했다.\n"
    "나는 세상을 잊을 수 있어도,\n"
    "그 눈과 그 미소만은\n"
    "끝내 잊지 못하리라."
)

_PROCESSING = "나는 세상이 변해도 그녀의 깊은 눈과 찬란한 미소만은 끝내 잊지 못한다."


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(_WELCOME)


@router.message(F.text)
async def handle_url(message: Message) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    text = (message.text or "").strip()

    # ── Rate limit ───────────────────────────────────────────────────────────
    try:
        rate_limiter.check(user_id)
    except RateLimitExceeded as exc:
        await message.reply(
            f"⏱ You're sending requests too fast. "
            f"Please wait <b>{exc.retry_after:.0f}s</b> before trying again."
        )
        return

    # ── URL validation ───────────────────────────────────────────────────────
    try:
        clean_url = validate_url(text)
    except URLValidationError as exc:
        await message.reply(f"❌ Invalid URL: {exc}")
        return

    platform = detect_platform(clean_url)
    if platform is None:
        await message.reply(
            "❌ Unsupported URL. Please send a Spotify or YouTube link."
        )
        return

    status_msg = await message.reply(_PROCESSING)

    session: aiohttp.ClientSession = build_session()
    try:
        orchestrator = Orchestrator(session)
        audio_path, metadata = await orchestrator.process_url(clean_url, platform)

        platform_icon = "🎵" if platform.value == "spotify" else "▶️"
        caption = (
            f"{platform_icon} <b>{_esc(metadata.title)}</b>\n"
            f"👤 {_esc(metadata.artist)}"
        )
        if metadata.album:
            caption += f"\n💿 {_esc(metadata.album)}"

        audio_file = FSInputFile(audio_path, filename=f"{metadata.display_name[:60]}.mp3")
        await message.answer_audio(
            audio=audio_file,
            caption=caption,
            title=metadata.title[:64],
            performer=metadata.artist[:64],
            duration=int(metadata.duration_seconds),
        )
        logger.info(
            "Audio sent",
            extra={"user_id": user_id, "track": metadata.display_name, "platform": platform},
        )

    except PrivateVideoError:
        await status_msg.edit_text("🔒 This video is private and cannot be downloaded.")
    except GeoBlockedError:
        await status_msg.edit_text("🌍 This content is geo-blocked in the server's region.")
    except FileTooLargeError as exc:
        await status_msg.edit_text(f"📦 {exc}")
    except DownloadError as exc:
        logger.warning("Download error", extra={"error": str(exc), "user_id": user_id})
        await status_msg.edit_text("❌ Download failed. Please try another link.")
    except AudioProcessingError as exc:
        logger.error("Audio processing error", extra={"error": str(exc), "user_id": user_id})
        await status_msg.edit_text("⚙️ Audio processing failed. Please try again later.")
    except Exception as exc:
        logger.exception("Unexpected error", extra={"user_id": user_id})
        await status_msg.edit_text(
            "😕 An unexpected error occurred. Please try again later."
        )
    finally:
        await session.close()
        try:
            await status_msg.delete()
        except Exception:
            pass


def _esc(text: str) -> str:
    """Minimal HTML escape for Telegram."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )
