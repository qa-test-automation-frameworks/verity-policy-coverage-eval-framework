"""Checks that reviewer-facing docs stay in sync with the datasets/reports they cite."""

from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path

import pytest

from verity.adversarial import load_probes
from verity.golden import load_golden

_GOLDEN_DIR = Path("datasets/golden")
_PROBES_PATH = Path("datasets/adversarial/probes.yaml")
_README_PATH = Path("README.md")
_CALIBRATION_REPORT_PATH = Path("docs/calibration-report.md")
_LABELED_PATH = Path("datasets/calibration/labeled.yaml")


class TestGoldenCaseCount:
    def test_readme_case_count_matches_loaded_cases(self) -> None:
        cases = load_golden(_GOLDEN_DIR)
        text = _README_PATH.read_text()
        m = re.search(r"covers (\d+) cases", text)
        assert m, "README should state the golden dataset size as 'covers N cases'"
        assert int(m.group(1)) == len(cases)


class TestProbeCorpusCounts:
    def test_header_probe_count_matches_loaded_probes(self) -> None:
        probes = load_probes(_PROBES_PATH)
        header = _PROBES_PATH.read_text().splitlines()[1]
        m = re.search(r"(\d+) probes across (\d+) categories", header)
        assert m, "probes.yaml header should state 'N probes across M categories'"
        stated_count, stated_categories = int(m.group(1)), int(m.group(2))
        assert stated_count == len(probes)
        assert stated_categories == len({p.category for p in probes})


class TestCalibrationReportConsistency:
    def test_report_headline_numbers_match_a_fresh_synthetic_run(self) -> None:
        if not _LABELED_PATH.exists():
            pytest.skip("calibration dataset not found")

        sys.path.insert(0, str(Path("scripts")))
        from run_calibration import _judge_family, _run_hermetic

        from verity.calibration import (
            compute_agreement,
            compute_self_bias,
            load_calibration,
        )
        from verity.config import JudgeConfig, Provider, Settings

        cases = load_calibration(_LABELED_PATH)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            settings = Settings(
                _env_file=None,
                provider=Provider.zai,
                model="glm-4.5",
                judge=JudgeConfig(
                    _env_file=None, provider=Provider.zai, model="glm-4.5", temperature=0.0
                ),
            )
        judge_scores = _run_hermetic(cases, settings)
        agreement = compute_agreement(cases, judge_scores)
        bias = compute_self_bias(cases, judge_scores, judge_family=_judge_family(settings))

        report_text = _CALIBRATION_REPORT_PATH.read_text()
        assert f"**{agreement.raw_agreement:.1%}**" in report_text
        assert f"**{agreement.cohen_kappa:.3f}**" in report_text
        assert f"**{bias.self_preference_delta:+.3f}**" in report_text
