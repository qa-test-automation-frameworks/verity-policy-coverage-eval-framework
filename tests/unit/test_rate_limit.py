"""Tests for strict rolling-window provider request pacing."""

from __future__ import annotations

import pytest

from verity.rate_limit import (
    NVIDIA_RATE_LIMIT_WINDOW_SECONDS,
    NVIDIA_REQUESTS_PER_MINUTE,
    RollingWindowRateLimiter,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_nvidia_default_uses_forty_requests_per_rolling_minute() -> None:
    assert NVIDIA_REQUESTS_PER_MINUTE == 40
    assert NVIDIA_RATE_LIMIT_WINDOW_SECONDS == 60.0


def test_rolling_window_waits_until_the_oldest_request_expires() -> None:
    clock = FakeClock()
    limiter = RollingWindowRateLimiter(2, 60.0, clock=clock.clock, sleep=clock.sleep)

    assert limiter.acquire() == 0.0
    assert limiter.acquire() == 0.0
    assert limiter.acquire() == 60.0
    assert clock.now == 60.0
    assert limiter.acquire() == 0.0


@pytest.mark.parametrize(
    ("limit", "window_seconds"),
    [(0, 60.0), (1, 0.0), (-1, 10.0)],
)
def test_rejects_invalid_rate_limit_configuration(limit: int, window_seconds: float) -> None:
    with pytest.raises(ValueError):
        RollingWindowRateLimiter(limit, window_seconds)
