"""Unit tests for historical trend storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from verity.cost import RunAccumulator, Usage
from verity.trends import append_trend, compute_trend_record, load_trend_history


class TestComputeTrendRecord:
    def test_all_passed(self) -> None:
        acc = RunAccumulator()
        acc.log_call("glm-4.5", Usage(100, 50, 150), latency_ms=5.0)
        node_results = {"test_a": "passed", "test_b": "passed"}
        record = compute_trend_record("deterministic", node_results, acc, latency_budget_ms=50.0)
        assert record.total == 2
        assert record.passed == 2
        assert record.failed == 0
        assert record.pass_rate == 1.0
        assert record.total_tokens == 150

    def test_partial_failures(self) -> None:
        acc = RunAccumulator()
        node_results = {"test_a": "passed", "test_b": "failed", "test_c": "passed"}
        record = compute_trend_record("deterministic", node_results, acc, latency_budget_ms=50.0)
        assert record.total == 3
        assert record.passed == 2
        assert record.failed == 1
        assert record.pass_rate == pytest.approx(2 / 3)

    def test_empty_results_defaults_to_full_pass_rate(self) -> None:
        acc = RunAccumulator()
        record = compute_trend_record("deterministic", {}, acc, latency_budget_ms=50.0)
        assert record.total == 0
        assert record.pass_rate == 1.0

    def test_retrieval_quality_passthrough(self) -> None:
        acc = RunAccumulator()
        record = compute_trend_record(
            "deterministic", {}, acc, latency_budget_ms=50.0, retrieval_quality=0.92
        )
        assert record.retrieval_quality == 0.92

    def test_run_id_and_git_sha_are_populated(self) -> None:
        acc = RunAccumulator()
        record = compute_trend_record("deterministic", {}, acc, latency_budget_ms=50.0)
        assert record.run_id
        assert record.git_sha

    def test_each_record_gets_a_distinct_run_id(self) -> None:
        acc = RunAccumulator()
        record_a = compute_trend_record("deterministic", {}, acc, latency_budget_ms=50.0)
        record_b = compute_trend_record("deterministic", {}, acc, latency_budget_ms=50.0)
        assert record_a.run_id != record_b.run_id

    def test_github_sha_env_var_takes_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_SHA", "abc123deadbeef")
        acc = RunAccumulator()
        record = compute_trend_record("deterministic", {}, acc, latency_budget_ms=50.0)
        assert record.git_sha == "abc123deadbeef"


class TestTrendPersistence:
    def test_append_and_load_round_trip(self, tmp_path: Path) -> None:
        acc = RunAccumulator()
        acc.log_call("glm-4.5", Usage(100, 50, 150), latency_ms=5.0)
        record = compute_trend_record(
            "deterministic", {"t1": "passed"}, acc, latency_budget_ms=50.0
        )
        append_trend(record, trends_dir=tmp_path)

        history = load_trend_history("deterministic", trends_dir=tmp_path)
        assert len(history) == 1
        assert history[0].total == 1
        assert history[0].total_tokens == 150

    def test_multiple_appends_accumulate_history(self, tmp_path: Path) -> None:
        acc = RunAccumulator()
        for _ in range(3):
            record = compute_trend_record(
                "deterministic", {"t1": "passed"}, acc, latency_budget_ms=50.0
            )
            append_trend(record, trends_dir=tmp_path)

        history = load_trend_history("deterministic", trends_dir=tmp_path)
        assert len(history) == 3

    def test_load_missing_history_returns_empty(self, tmp_path: Path) -> None:
        assert load_trend_history("nonexistent", trends_dir=tmp_path) == []

    def test_tiers_stored_separately(self, tmp_path: Path) -> None:
        acc = RunAccumulator()
        det_record = compute_trend_record("deterministic", {"t1": "passed"}, acc, 50.0)
        sem_record = compute_trend_record("semantic", {"t1": "passed"}, acc, 30_000.0)
        append_trend(det_record, trends_dir=tmp_path)
        append_trend(sem_record, trends_dir=tmp_path)

        assert len(load_trend_history("deterministic", trends_dir=tmp_path)) == 1
        assert len(load_trend_history("semantic", trends_dir=tmp_path)) == 1
