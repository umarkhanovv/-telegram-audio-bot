"""
Telegram message handlers.
"""
import logging
from pathlib import Path

import aiohttp
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile

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
    "🎵 <b>Audio Bot</b>\n\n"
    "Send me a YouTube track URL and I will return the audio as an MP3 file.\n\n"
    "Just paste any YouTube link and I will handle the rest!"
)

_PROCESSING = "⏳ Processing your request, please wait..."


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(_WELCOME)


@router.message(F.text)
async def handle_url(message: Message) -> None:
    user_id = message.from_user.id  # type: ignore[union-attr]
    text = (message.text or "").strip()

    try:
        rate_limiter.check(user_id)
    except RateLimitExceeded as exc:
        await message.reply(
            f"You are sending requests too fast. Please wait {exc.retry_after:.0f} seconds."
        )
        return

    try:
        clean_url = validate_url(text)
    except URLValidationError as exc:
        await message.reply(f"Invalid URL: {exc}")
        return

    platform = detect_platform(clean_url)
    if platform is None:
        await message.reply("Unsupported URL. Please send a Spotify or YouTube link.")
        return

    status_msg = await message.reply(_PROCESSING)

    session: aiohttp.ClientSession = build_session()
    try:
        orchestrator = Orchestrator(session)
        audio_path, metadata = await orchestrator.process_url(clean_url, platform)

        caption = f"🎵 {_esc(metadata.title)}\n👤 {_esc(metadata.artist)}"
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
        await status_msg.edit_text("This video is private and cannot be downloaded.")
    except GeoBlockedError:
        await status_msg.edit_text("This content is not available in the server region.")
    except FileTooLargeError:
        await status_msg.edit_text(f"File exceeds the {50}MB limit.")
    except DownloadError:
        await status_msg.edit_text("Download failed. Please try a different link.")
    except AudioProcessingError:
        await status_msg.edit_text("Audio processing failed. Please try again later.")
    except Exception:
        logger.exception("Unexpected error", extra={"user_id": user_id})
        await status_msg.edit_text("Something went wrong. Please try again later.")
    finally:
        await session.close()
        try:
            await status_msg.delete()
        except Exception:
            pass


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )
