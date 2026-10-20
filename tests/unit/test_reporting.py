"""Unit tests for verity.reporting — cost summary rendering and step-summary output."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from verity.cost import RunAccumulator, Usage, reset_current_test_id, set_current_test_id
from verity.reporting import (
    build_usage_report,
    render_cost_summary,
    render_usage_summary,
    write_step_summary,
)


def _log(
    acc: RunAccumulator,
    label: str,
    prompt: int = 100,
    completion: int = 50,
    model: str = "fake/model",
) -> None:
    acc.log_call(
        model=model,
        usage=Usage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        ),
        latency_ms=10.0,
        label=label,
    )


class TestRenderCostSummary:
    def test_empty_accumulator_returns_no_calls_message(self) -> None:
        acc = RunAccumulator()
        result = render_cost_summary(acc)
        assert "No LLM calls recorded" in result

    def test_single_record_renders_label_row(self) -> None:
        acc = RunAccumulator()
        _log(acc, "agent.first-turn")
        result = render_cost_summary(acc)
        assert "agent.first-turn" in result
        assert "| Calls |" in result

    def test_total_row_aggregates_multiple_records(self) -> None:
        acc = RunAccumulator()
        _log(acc, "turn-1", prompt=100, completion=50)
        _log(acc, "turn-2", prompt=200, completion=80)
        result = render_cost_summary(acc)
        assert "Total" in result
        assert "430" in result  # 150 + 280 total tokens

    def test_multiple_labels_each_appear(self) -> None:
        acc = RunAccumulator()
        _log(acc, "judge")
        _log(acc, "retrieval")
        result = render_cost_summary(acc)
        assert "judge" in result
        assert "retrieval" in result

    def test_unlabeled_record_uses_fallback_label(self) -> None:
        acc = RunAccumulator()
        _log(acc, "")
        result = render_cost_summary(acc)
        assert "unlabeled" in result

    def test_cost_appears_in_table(self) -> None:
        acc = RunAccumulator()
        _log(acc, "x", model="glm-4.5")
        result = render_cost_summary(acc)
        assert "$" in result

    def test_unpriced_model_renders_as_unpriced_not_zero(self) -> None:
        acc = RunAccumulator()
        _log(acc, "x", model="fake/model")
        result = render_cost_summary(acc)
        assert "unpriced" in result
        assert "$0.000000" not in result

    def test_mixed_priced_and_unpriced_labels_render_independently(self) -> None:
        acc = RunAccumulator()
        _log(acc, "priced", model="glm-4.5")
        _log(acc, "unpriced", model="fake/model")
        result = render_cost_summary(acc)
        assert "unpriced" in result
        assert "$0.000000" not in result


class TestUsageReport:
    def test_reports_per_test_and_suite_with_sut_judge_and_failure(self) -> None:
        acc = RunAccumulator()
        token = set_current_test_id("tests/semantic/test_x.py::test_case")
        try:
            sut = acc.begin_request("sut/model", label="agent-first-turn")
            acc.finish_request(sut, latency_ms=20, usage=Usage(100, 25, 125))
            acc.log_call(
                "sut/model",
                Usage(100, 25, 125),
                latency_ms=20,
                label="agent-first-turn",
                request_event=sut,
            )
            judge = acc.begin_request("judge/model", label="judge")
            acc.finish_request(judge, latency_ms=30, usage=Usage(80, 20, 100))
            acc.log_call(
                "judge/model",
                Usage(80, 20, 100),
                latency_ms=30,
                label="judge",
                request_event=judge,
            )
            failed = acc.begin_request("judge/model", label="judge")
            acc.finish_request(failed, latency_ms=5, error=TimeoutError())
        finally:
            reset_current_test_id(token)

        report = build_usage_report(acc, {"tests/semantic/test_x.py::test_case": "passed"})
        test_stats = report["by_test"]["tests/semantic/test_x.py::test_case"]
        assert test_stats["requests"] == 3
        assert test_stats["succeeded"] == 2
        assert test_stats["failed"] == 1
        assert test_stats["total_tokens"] == 225
        assert report["suite"]["total_tokens"] == 225
        assert report["suite"]["requests"] == 3

        summary = render_usage_summary(report)
        assert "1 / 2" in summary
        assert "225" in summary
        assert "test_case" in summary
        assert "TimeoutError" not in summary
        assert report["privacy"]["request_and_response_bodies_included"] is False
        assert '"request_id"' in json.dumps(report)


class TestWriteStepSummary:
    def test_writes_to_local_file_when_no_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()
        write_step_summary("# Test\n")
        content = (tmp_path / "reports" / "cost-summary-local.md").read_text()
        assert "# Test" in content

    def test_writes_to_github_step_summary_when_env_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        summary_file = tmp_path / "step_summary.md"
        summary_file.touch()
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
        write_step_summary("hello CI\n")
        assert "hello CI" in summary_file.read_text()

    def test_appends_when_called_twice(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()
        write_step_summary("first\n")
        write_step_summary("second\n")
        content = (tmp_path / "reports" / "cost-summary-local.md").read_text()
        assert "first" in content
        assert "second" in content

    def test_first_write_truncates_stale_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        monkeypatch.chdir(tmp_path)
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "cost-summary-local.md").write_text("stale from a previous run\n")
        write_step_summary("fresh\n")
        content = (reports_dir / "cost-summary-local.md").read_text()
        assert "stale" not in content
        assert "fresh" in content
