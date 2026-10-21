"""Thread-safe rolling-window request pacing for hosted NVIDIA NIM calls."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from threading import Lock

NVIDIA_REQUESTS_PER_MINUTE = 40
NVIDIA_RATE_LIMIT_WINDOW_SECONDS = 60.0


class RollingWindowRateLimiter:
    """Wait until a request fits within a strict rolling time window."""

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._sleep = sleep
        self._request_times: deque[float] = deque()
        self._lock = Lock()

    def acquire(self) -> float:
        """Reserve a request slot and return time spent waiting in seconds."""
        started = self._clock()
        while True:
            with self._lock:
                now = self._clock()
                while self._request_times and now - self._request_times[0] >= self._window_seconds:
                    self._request_times.popleft()
                if len(self._request_times) < self._limit:
                    self._request_times.append(now)
                    return max(0.0, self._clock() - started)
                delay = self._request_times[0] + self._window_seconds - now
            self._sleep(max(delay, 0.0))
