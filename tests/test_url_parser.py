"""
Tests for URL validation and platform detection.
Run with: pytest tests/
"""
import pytest
from app.utils.url_parser import (
    detect_platform,
    validate_url,
    extract_spotify_track_id,
    extract_youtube_video_id,
    Platform,
    URLValidationError,
)


class TestDetectPlatform:
    def test_spotify_track(self):
        url = "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC"
        assert detect_platform(url) == Platform.SPOTIFY

    def test_spotify_intl(self):
        url = "https://open.spotify.com/intl-de/track/4uLU6hMCjMI75M1A2tKUQC"
        assert detect_platform(url) == Platform.SPOTIFY

    def test_youtube_watch(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert detect_platform(url) == Platform.YOUTUBE

    def test_youtu_be(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert detect_platform(url) == Platform.YOUTUBE

    def test_unknown_returns_none(self):
        assert detect_platform("https://soundcloud.com/track/abc") is None


class TestValidateUrl:
    def test_valid_spotify(self):
        url = "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC"
        assert validate_url(url) == url

    def test_rejects_http_localhost(self):
        with pytest.raises(URLValidationError):
            validate_url("http://localhost/evil")

    def test_rejects_private_ip(self):
        with pytest.raises(URLValidationError):
            validate_url("http://192.168.1.1/steal-secrets")

    def test_rejects_unknown_host(self):
        with pytest.raises(URLValidationError):
            validate_url("https://evil.com/track/123")

    def test_rejects_too_long(self):
        with pytest.raises(URLValidationError):
            validate_url("https://open.spotify.com/" + "a" * 2048)

    def test_rejects_ftp_scheme(self):
        with pytest.raises(URLValidationError):
            validate_url("ftp://open.spotify.com/track/123")


class TestExtractIds:
    def test_spotify_id(self):
        url = "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC"
        assert extract_spotify_track_id(url) == "4uLU6hMCjMI75M1A2tKUQC"

    def test_youtube_watch_id(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_youtube_short_id(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert extract_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_invalid_spotify_raises(self):
        with pytest.raises(URLValidationError):
            extract_spotify_track_id("https://open.spotify.com/playlist/abc")


class TestRateLimiter:
    def test_allows_within_limit(self):
        from app.utils.rate_limiter import RateLimiter
        rl = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            rl.check(user_id=9999)  # Should not raise

    def test_blocks_over_limit(self):
        from app.utils.rate_limiter import RateLimiter, RateLimitExceeded
        rl = RateLimiter(max_requests=2, window_seconds=60)
        rl.check(1)
        rl.check(1)
        with pytest.raises(RateLimitExceeded):
            rl.check(1)

    def test_different_users_independent(self):
        from app.utils.rate_limiter import RateLimiter
        rl = RateLimiter(max_requests=1, window_seconds=60)
        rl.check(1)
        rl.check(2)  # Different user — should not raise
