"""Unit tests for latency budget checks."""

from __future__ import annotations

from verity.cost import RunAccumulator, Usage
from verity.latency import DETERMINISTIC_BUDGET_MS, check_latency_budget


class TestLatencyBudget:
    def test_empty_accumulator_passes(self) -> None:
        acc = RunAccumulator()
        report = check_latency_budget(acc, DETERMINISTIC_BUDGET_MS)
        assert report.passed
        assert report.n == 0

    def test_all_calls_within_budget_pass(self) -> None:
        acc = RunAccumulator()
        acc.log_call("glm-4.5", Usage(10, 5, 15), latency_ms=1.0, label="a")
        acc.log_call("glm-4.5", Usage(10, 5, 15), latency_ms=2.0, label="b")
        report = check_latency_budget(acc, budget_ms=50.0)
        assert report.passed
        assert not report.violations

    def test_call_over_budget_fails(self) -> None:
        acc = RunAccumulator()
        acc.log_call("glm-4.5", Usage(10, 5, 15), latency_ms=100.0, label="slow-call")
        report = check_latency_budget(acc, budget_ms=50.0)
        assert not report.passed
        assert len(report.violations) == 1
        assert report.violations[0].label == "slow-call"
        assert report.violations[0].latency_ms == 100.0

    def test_percentiles_computed(self) -> None:
        acc = RunAccumulator()
        for ms in [10.0, 20.0, 30.0, 40.0, 50.0]:
            acc.log_call("glm-4.5", Usage(10, 5, 15), latency_ms=ms)
        report = check_latency_budget(acc, budget_ms=1000.0)
        assert report.max_ms == 50.0
        assert report.p50_ms in (20.0, 30.0, 40.0)  # median-ish depending on interpolation
        assert report.p95_ms >= report.p50_ms

    def test_only_over_budget_calls_are_violations(self) -> None:
        acc = RunAccumulator()
        acc.log_call("glm-4.5", Usage(10, 5, 15), latency_ms=10.0, label="fast")
        acc.log_call("glm-4.5", Usage(10, 5, 15), latency_ms=200.0, label="slow")
        report = check_latency_budget(acc, budget_ms=50.0)
        assert len(report.violations) == 1
        assert report.violations[0].label == "slow"
