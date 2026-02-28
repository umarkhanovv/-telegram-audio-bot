"""
Shared async HTTP client with:
- Retry with exponential backoff
- Redirect limits
- Timeouts
- No private-IP redirects (SSRF guard)
"""
import asyncio
import logging
from typing import Any, Optional

import aiohttp
from aiohttp import ClientSession, TCPConnector

from app.config.settings import settings
from app.utils.url_parser import _PRIVATE_HOST_RE

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"HTTP {status}: {message}")


class SSRFAttemptError(Exception):
    pass


async def _check_redirect(session, ctx, params):
    """Hook: validate redirect URL is not private."""
    host = params.url.host or ""
    if _PRIVATE_HOST_RE.match(host):
        raise SSRFAttemptError(f"Redirect to private host blocked: {host}")


def build_session() -> ClientSession:
    connector = TCPConnector(
        limit=20,
        ssl=True,
    )
    timeout = aiohttp.ClientTimeout(total=settings.HTTP_TIMEOUT_SECONDS)
    return ClientSession(
        connector=connector,
        timeout=timeout,
        trust_env=False,
        trace_configs=[_build_trace_config()],
    )


def _build_trace_config() -> aiohttp.TraceConfig:
    tc = aiohttp.TraceConfig()
    tc.on_request_redirect.append(_check_redirect)  # type: ignore[arg-type]
    return tc


async def fetch_json(
    session: ClientSession,
    url: str,
    *,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
) -> Any:
    """GET JSON with retry."""
    return await _request_with_retry(
        session, "GET", url, headers=headers, params=params
    )


async def _request_with_retry(
    session: ClientSession,
    method: str,
    url: str,
    *,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    data: Any = None,
    attempts: int = settings.HTTP_RETRY_ATTEMPTS,
    backoff: float = settings.HTTP_RETRY_BACKOFF,
) -> Any:
    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(1, attempts + 1):
        try:
            async with session.request(
                method,
                url,
                headers=headers,
                params=params,
                data=data,
                allow_redirects=True,
                max_redirects=settings.HTTP_MAX_REDIRECTS,
            ) as resp:
                if resp.status in _RETRYABLE_STATUSES and attempt < attempts:
                    wait = backoff ** attempt
                    logger.warning(
                        "Retryable HTTP status",
                        extra={"status": resp.status, "attempt": attempt, "wait": wait},
                    )
                    await asyncio.sleep(wait)
                    continue
                if resp.status >= 400:
                    body = await resp.text()
                    raise HttpError(resp.status, body[:200])
                return await resp.json(content_type=None)
        except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as exc:
            last_exc = exc
            if attempt < attempts:
                wait = backoff ** attempt
                logger.warning(
                    "Connection error, retrying",
                    extra={"error": str(exc), "attempt": attempt, "wait": wait},
                )
                await asyncio.sleep(wait)
    raise last_exc
