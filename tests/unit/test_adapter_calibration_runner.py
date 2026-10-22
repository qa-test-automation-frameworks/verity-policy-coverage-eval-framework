"""Safety-bound tests for the runtime-adapter calibration runner."""

from __future__ import annotations

from threading import Lock

import pytest
from scripts.run_adapter_calibration import (
    BudgetedJudge,
    RateCeilingError,
    RequestBoundAccumulator,
    RequestCeilingError,
)
from verity.cost import RunAccumulator, Usage


def test_request_and_rate_ceilings_reject_before_recording_an_extra_call() -> None:
    request_limited = RequestBoundAccumulator(max_requests=1, max_requests_per_minute=2)
    request_limited.begin_request(model="openai/gpt-4o-mini")
    with pytest.raises(RequestCeilingError):
        request_limited.begin_request(model="openai/gpt-4o-mini")
    assert len(request_limited.requests) == 1

    rate_limited = RequestBoundAccumulator(max_requests=2, max_requests_per_minute=1)
    rate_limited.begin_request(model="openai/gpt-4o-mini")
    with pytest.raises(RateCeilingError):
        rate_limited.begin_request(model="openai/gpt-4o-mini")
    assert len(rate_limited.requests) == 1


def test_unreported_provider_attempt_keeps_its_cost_reservation() -> None:
    judge = object.__new__(BudgetedJudge)
    judge._accumulator = RunAccumulator()
    judge._reserved_usd = 0.75
    judge._lock = Lock()

    event = judge._accumulator.begin_request(model="openai/gpt-4o-mini")
    judge._accumulator.finish_request(
        event, latency_ms=1.0, error=TimeoutError("provider did not return usage")
    )
    judge._release_if_fully_accounted(0, 0.5)

    assert judge._reserved_usd == pytest.approx(0.75)


def test_fully_reported_provider_attempt_releases_unused_reservation() -> None:
    judge = object.__new__(BudgetedJudge)
    judge._accumulator = RunAccumulator()
    judge._reserved_usd = 0.75
    judge._lock = Lock()

    event = judge._accumulator.begin_request(model="openai/gpt-4o-mini")
    judge._accumulator.finish_request(
        event, latency_ms=1.0, usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    )
    judge._release_if_fully_accounted(0, 0.5)

    assert judge._reserved_usd == pytest.approx(0.25)
