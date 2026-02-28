import pytest
from app.services.youtube import _iso_duration_to_ms


@pytest.mark.parametrize("duration,expected_ms", [
    ("PT3M30S", 210_000),
    ("PT1H2M3S", 3723_000),
    ("PT45S", 45_000),
    ("PT0S", 0),
    ("PT1H", 3_600_000),
    ("PT2M", 120_000),
])
def test_iso_duration_to_ms(duration, expected_ms):
    assert _iso_duration_to_ms(duration) == expected_ms
