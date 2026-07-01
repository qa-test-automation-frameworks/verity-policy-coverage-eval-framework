"""Unit tests for the per-module coverage gate script."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_module_coverage import check_module_coverage


def _write_coverage_json(tmp_path: Path, files: dict[str, float]) -> Path:
    data = {"files": {path: {"summary": {"percent_covered": pct}} for path, pct in files.items()}}
    out = tmp_path / "coverage.json"
    out.write_text(json.dumps(data))
    return out


class TestCheckModuleCoverage:
    def test_all_modules_above_threshold_passes(self, tmp_path: Path) -> None:
        cov = _write_coverage_json(
            tmp_path,
            {
                "src/sut/agent.py": 82.0,
                "src/sut/retriever.py": 97.0,
                "src/verity/metrics/ragas_metrics.py": 84.0,
                "src/verity/metrics/deepeval_metrics.py": 71.0,
                "src/verity/tracing.py": 88.0,
                "src/verity/reporting.py": 100.0,
            },
        )
        failures = check_module_coverage(cov)
        assert failures == []

    def test_module_below_threshold_fails(self, tmp_path: Path) -> None:
        cov = _write_coverage_json(
            tmp_path,
            {
                "src/sut/agent.py": 50.0,
                "src/sut/retriever.py": 97.0,
                "src/verity/metrics/ragas_metrics.py": 84.0,
                "src/verity/metrics/deepeval_metrics.py": 71.0,
                "src/verity/tracing.py": 88.0,
                "src/verity/reporting.py": 100.0,
            },
        )
        failures = check_module_coverage(cov)
        assert len(failures) == 1
        assert "src/sut/agent.py" in failures[0]
        assert "50.0%" in failures[0]

    def test_missing_module_from_report_fails(self, tmp_path: Path) -> None:
        cov = _write_coverage_json(tmp_path, {"src/sut/agent.py": 90.0})
        failures = check_module_coverage(cov)
        # 5 of the 6 required modules are missing from this report.
        assert len(failures) == 5
        assert any("not found in coverage report" in f for f in failures)

    def test_multiple_modules_below_threshold_all_reported(self, tmp_path: Path) -> None:
        cov = _write_coverage_json(
            tmp_path,
            {
                "src/sut/agent.py": 10.0,
                "src/sut/retriever.py": 10.0,
                "src/verity/metrics/ragas_metrics.py": 84.0,
                "src/verity/metrics/deepeval_metrics.py": 71.0,
                "src/verity/tracing.py": 88.0,
                "src/verity/reporting.py": 100.0,
            },
        )
        failures = check_module_coverage(cov)
        assert len(failures) == 2
