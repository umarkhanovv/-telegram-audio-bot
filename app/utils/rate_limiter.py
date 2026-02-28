"""
In-memory sliding-window rate limiter per user.
Thread-safe for asyncio (no locks needed — single-threaded event loop).
"""
import asyncio
import time
from collections import defaultdict, deque
from functools import wraps
from typing import Callable

from app.config.settings import settings


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after:.0f}s")


class RateLimiter:
    """Sliding window counter per user_id."""

    def __init__(
        self,
        max_requests: int = settings.RATE_LIMIT_REQUESTS,
        window_seconds: int = settings.RATE_LIMIT_WINDOW_SECONDS,
    ):
        self._max = max_requests
        self._window = window_seconds
        self._buckets: dict[int, deque[float]] = defaultdict(deque)

    def check(self, user_id: int) -> None:
        """Raise RateLimitExceeded if the user is over the limit."""
        now = time.monotonic()
        window_start = now - self._window
        bucket = self._buckets[user_id]

        # Drop timestamps outside the window
        while bucket and bucket[0] < window_start:
            bucket.popleft()

        if len(bucket) >= self._max:
            oldest = bucket[0]
            retry_after = oldest - window_start
            raise RateLimitExceeded(retry_after=retry_after)

        bucket.append(now)

    def reset(self, user_id: int) -> None:
        self._buckets.pop(user_id, None)


# Module-level singleton
rate_limiter = RateLimiter()
