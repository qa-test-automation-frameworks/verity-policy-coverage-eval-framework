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
        """When the committed report is a synthetic replay, its headline
        numbers must exactly match a fresh hermetic re-run (the report is
        fully reproducible in that mode)."""
        if not _LABELED_PATH.exists():
            pytest.skip("calibration dataset not found")

        report_text = _CALIBRATION_REPORT_PATH.read_text()
        if "**Mode:** synthetic replay" not in report_text:
            pytest.skip("committed report is a live run, not a synthetic replay")

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

        assert f"**{agreement.raw_agreement:.1%}**" in report_text
        assert f"**{agreement.cohen_kappa:.3f}**" in report_text
        assert f"**{bias.self_preference_delta:+.3f}**" in report_text
        traceability_match = re.search(
            r"- \*\*Self-preference delta\*\*: ([+-][\d.]+)", report_text
        )
        assert traceability_match, "no Self-preference delta bullet found in report"
        assert float(traceability_match.group(1)) == pytest.approx(
            bias.self_preference_delta, abs=5e-4
        )

    def test_report_headline_numbers_are_derived_from_its_own_case_table(self) -> None:
        """Regardless of synthetic vs. live mode, the report's headline
        agreement/kappa/self-bias numbers must be exactly what
        compute_agreement/compute_self_bias produce from the report's own
        embedded per-case score table — catching rendering bugs (e.g. a
        dropped sign) independent of whether the underlying judge run is
        reproducible."""
        if not _LABELED_PATH.exists():
            pytest.skip("calibration dataset not found")

        report_text = _CALIBRATION_REPORT_PATH.read_text()

        from verity.calibration import compute_agreement, compute_self_bias, load_calibration

        cases_by_id = {c.id: c for c in load_calibration(_LABELED_PATH)}

        row_re = re.compile(
            r"\|\s*`([^`]+)`\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|"
        )
        ordered_cases = []
        judge_scores = []
        for case_id, _metric, family, _human, judge in row_re.findall(report_text):
            case = cases_by_id.get(case_id)
            if case is None:
                continue
            assert case.output_family == family, f"{case_id}: family mismatch in table"
            ordered_cases.append(case)
            judge_scores.append(float(judge))

        assert ordered_cases, "no parseable rows found in the Individual Case Scores table"

        judge_model_match = re.search(r"\*\*Judge model:\*\*\s*`([^`]+)`", report_text)
        assert judge_model_match, "no Judge model line found in report"
        judge_family = "glm" if "glm" in judge_model_match.group(1).lower() else "other"
        agreement = compute_agreement(ordered_cases, judge_scores)
        bias = compute_self_bias(ordered_cases, judge_scores, judge_family=judge_family)

        assert f"**{agreement.raw_agreement:.1%}**" in report_text
        assert f"**{agreement.cohen_kappa:.3f}**" in report_text
        assert f"**{bias.self_preference_delta:+.3f}**" in report_text
        traceability_match = re.search(
            r"- \*\*Self-preference delta\*\*: ([+-][\d.]+)", report_text
        )
        assert traceability_match, "no Self-preference delta bullet found in report"
        assert float(traceability_match.group(1)) == pytest.approx(
            bias.self_preference_delta, abs=5e-4
        )


class TestPlanParameterConsistency:
    def test_agent_plan_params_match_definitions_table(self) -> None:
        from sut.agent import _PLAN_PARAMS

        text = Path("src/sut/corpus/definitions.md").read_text(encoding="utf-8")
        rows = re.findall(
            r"\| (Bronze|Silver|Gold) \| \$[\d,]+ \| \$([\d,]+) \| \$([\d,]+) \| (\d+)% \|",
            text,
        )
        parsed = {
            plan.lower(): {
                "plan_deductible": float(deductible.replace(",", "")),
                "plan_oop_max": float(oop_max.replace(",", "")),
                "coinsurance_member": float(coinsurance) / 100.0,
            }
            for plan, deductible, oop_max, coinsurance in rows
        }

        assert parsed == _PLAN_PARAMS
