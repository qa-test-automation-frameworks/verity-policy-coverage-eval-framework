"""Unit tests for verity.reporting — cost summary rendering and step-summary output."""

from __future__ import annotations

from pathlib import Path

import pytest

from verity.cost import RunAccumulator, Usage
from verity.reporting import render_cost_summary, write_step_summary


def _log(acc: RunAccumulator, label: str, prompt: int = 100, completion: int = 50) -> None:
    acc.log_call(
        model="fake/model",
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
        _log(acc, "x")
        result = render_cost_summary(acc)
        assert "$" in result


class TestWriteStepSummary:
    def test_writes_to_local_file_when_no_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "reports").mkdir()
        write_step_summary("# Test\n")
        content = (tmp_path / "reports" / "cost-summary.md").read_text()
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
        content = (tmp_path / "reports" / "cost-summary.md").read_text()
        assert "first" in content
        assert "second" in content
