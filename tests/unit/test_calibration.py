"""Unit tests for the judge calibration module."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from verity.calibration import (
    CalibrationCase,
    build_scoring_prompt,
    compute_agreement,
    compute_self_bias,
    load_calibration,
    parse_judge_score,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _case(
    metric: str = "completeness",
    human_score: float = 0.8,
    human_pass: bool = True,
    output_family: str = "glm",
) -> CalibrationCase:
    return CalibrationCase(
        id="test-case",
        metric=metric,  # type: ignore[arg-type]
        query="Test query?",
        context=["Policy snippet."],
        candidate_output="Test answer.",
        output_family=output_family,  # type: ignore[arg-type]
        human_score=human_score,
        human_pass=human_pass,
    )


# ---------------------------------------------------------------------------
# CalibrationCase schema
# ---------------------------------------------------------------------------


class TestCalibrationCase:
    def test_valid_case_parses(self) -> None:
        c = _case()
        assert c.metric == "completeness"
        assert c.human_pass is True

    def test_invalid_metric_raises(self) -> None:
        with pytest.raises(ValidationError):
            CalibrationCase(
                id="x",
                metric="invalid",  # type: ignore[arg-type]
                query="q",
                candidate_output="a",
                output_family="glm",
                human_score=0.5,
                human_pass=True,
            )

    def test_invalid_output_family_raises(self) -> None:
        with pytest.raises(ValidationError):
            CalibrationCase(
                id="x",
                metric="refusal",
                query="q",
                candidate_output="a",
                output_family="anthropic",  # type: ignore[arg-type]
                human_score=0.5,
                human_pass=True,
            )

    def test_context_defaults_empty(self) -> None:
        c = CalibrationCase(
            id="x",
            metric="faithfulness",
            query="q",
            candidate_output="a",
            output_family="other",
            human_score=0.7,
            human_pass=True,
        )
        assert c.context == []

    def test_rationale_defaults_empty(self) -> None:
        c = _case()
        assert c.rationale == ""


# ---------------------------------------------------------------------------
# load_calibration
# ---------------------------------------------------------------------------


class TestLoadCalibration:
    def test_loads_real_dataset(self) -> None:
        path = Path("datasets/calibration/labeled.yaml")
        cases = load_calibration(path)
        assert len(cases) == 32

    def test_all_ids_unique(self) -> None:
        path = Path("datasets/calibration/labeled.yaml")
        cases = load_calibration(path)
        ids = [c.id for c in cases]
        assert len(ids) == len(set(ids))

    def test_all_metrics_present(self) -> None:
        path = Path("datasets/calibration/labeled.yaml")
        cases = load_calibration(path)
        metrics = {c.metric for c in cases}
        assert metrics == {"completeness", "disambiguation", "refusal", "faithfulness"}

    def test_eight_per_metric(self) -> None:
        path = Path("datasets/calibration/labeled.yaml")
        cases = load_calibration(path)
        for metric in ("completeness", "disambiguation", "refusal", "faithfulness"):
            count = sum(1 for c in cases if c.metric == metric)
            assert count == 8, f"Expected 8 cases for {metric}, got {count}"

    def test_balanced_output_families(self) -> None:
        path = Path("datasets/calibration/labeled.yaml")
        cases = load_calibration(path)
        glm = sum(1 for c in cases if c.output_family == "glm")
        other = sum(1 for c in cases if c.output_family == "other")
        assert glm == other == 16

    def test_human_scores_in_range(self) -> None:
        path = Path("datasets/calibration/labeled.yaml")
        cases = load_calibration(path)
        for c in cases:
            assert 0.0 <= c.human_score <= 1.0, f"Score out of range for {c.id}"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_calibration(tmp_path / "nonexistent.yaml")


# ---------------------------------------------------------------------------
# compute_agreement
# ---------------------------------------------------------------------------


class TestComputeAgreement:
    def _cases_and_scores(self) -> tuple[list[CalibrationCase], list[float]]:
        # 4 cases: 2 agree, 2 disagree (raw_agreement = 0.5)
        cases = [
            _case(metric="completeness", human_score=0.8, human_pass=True, output_family="glm"),
            _case(metric="completeness", human_score=0.2, human_pass=False, output_family="other"),
            _case(metric="refusal", human_score=0.9, human_pass=True, output_family="glm"),
            _case(metric="refusal", human_score=0.1, human_pass=False, output_family="other"),
        ]
        # judge says: pass, pass, fail, fail → agree on [0]=True✓ and [3]=False✓
        judge_scores = [0.8, 0.7, 0.3, 0.2]
        return cases, judge_scores

    def test_raw_agreement(self) -> None:
        cases, scores = self._cases_and_scores()
        report = compute_agreement(cases, scores)
        assert report.raw_agreement == pytest.approx(0.5)

    def test_n(self) -> None:
        cases, scores = self._cases_and_scores()
        report = compute_agreement(cases, scores)
        assert report.n == 4

    def test_mae(self) -> None:
        cases = [_case(human_score=0.8), _case(human_score=0.2)]
        scores = [1.0, 0.0]
        report = compute_agreement(cases, scores)
        # |1.0 - 0.8| + |0.0 - 0.2| = 0.2 + 0.2 = 0.4; mean = 0.2
        assert report.mae == pytest.approx(0.2)

    def test_perfect_agreement_kappa_one(self) -> None:
        cases = [
            _case(human_score=0.9, human_pass=True),
            _case(human_score=0.1, human_pass=False),
            _case(human_score=0.8, human_pass=True),
            _case(human_score=0.2, human_pass=False),
        ]
        scores = [0.9, 0.1, 0.8, 0.2]
        report = compute_agreement(cases, scores)
        assert report.raw_agreement == pytest.approx(1.0)
        assert report.cohen_kappa == pytest.approx(1.0)

    def test_per_metric_breakdown(self) -> None:
        cases, scores = self._cases_and_scores()
        report = compute_agreement(cases, scores)
        assert "completeness" in report.per_metric
        assert "refusal" in report.per_metric
        assert report.per_metric["completeness"]["n"] == 2.0

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="zero cases"):
            compute_agreement([], [])

    def test_length_mismatch_raises(self) -> None:
        cases = [_case()]
        with pytest.raises(ValueError, match="same length"):
            compute_agreement(cases, [0.5, 0.6])

    def test_str_repr(self) -> None:
        cases = [_case(human_score=0.8, human_pass=True)]
        report = compute_agreement(cases, [0.9])
        s = str(report)
        assert "Raw agreement" in s
        assert "kappa" in s


# ---------------------------------------------------------------------------
# compute_self_bias
# ---------------------------------------------------------------------------


class TestComputeSelfBias:
    def test_positive_self_preference(self) -> None:
        cases = [
            _case(human_score=0.6, output_family="glm"),  # judge: 0.8 → delta +0.2
            _case(human_score=0.7, output_family="glm"),  # judge: 0.9 → delta +0.2
            _case(human_score=0.7, output_family="other"),  # judge: 0.7 → delta 0.0
            _case(human_score=0.8, output_family="other"),  # judge: 0.8 → delta 0.0
        ]
        judge_scores = [0.8, 0.9, 0.7, 0.8]
        report = compute_self_bias(cases, judge_scores)
        assert report.mean_delta_own_family == pytest.approx(0.2)
        assert report.mean_delta_other_family == pytest.approx(0.0)
        assert report.self_preference_delta == pytest.approx(0.2)

    def test_zero_bias(self) -> None:
        cases = [
            _case(human_score=0.7, output_family="glm"),
            _case(human_score=0.7, output_family="other"),
        ]
        judge_scores = [0.7, 0.7]
        report = compute_self_bias(cases, judge_scores)
        assert report.self_preference_delta == pytest.approx(0.0)

    def test_negative_self_preference(self) -> None:
        cases = [
            _case(human_score=0.8, output_family="glm"),  # judge: 0.7 → delta -0.1
            _case(human_score=0.5, output_family="other"),  # judge: 0.8 → delta +0.3
        ]
        judge_scores = [0.7, 0.8]
        report = compute_self_bias(cases, judge_scores)
        assert report.self_preference_delta == pytest.approx(-0.4)

    def test_n_own_n_other(self) -> None:
        cases = [
            _case(output_family="glm"),
            _case(output_family="glm"),
            _case(output_family="other"),
        ]
        report = compute_self_bias(cases, [0.5, 0.5, 0.5])
        assert report.n_own == 2
        assert report.n_other == 1

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            compute_self_bias([_case()], [0.5, 0.6])

    def test_str_repr(self) -> None:
        cases = [
            _case(human_score=0.7, output_family="glm"),
            _case(human_score=0.7, output_family="other"),
        ]
        report = compute_self_bias(cases, [0.8, 0.7])
        s = str(report)
        assert "Self-Bias" in s
        assert "delta" in s


# ---------------------------------------------------------------------------
# parse_judge_score
# ---------------------------------------------------------------------------


class TestParseJudgeScore:
    def test_standard_format(self) -> None:
        assert parse_judge_score("Score: 8") == pytest.approx(0.8)

    def test_lowercase(self) -> None:
        assert parse_judge_score("score: 7") == pytest.approx(0.7)

    def test_with_surrounding_text(self) -> None:
        text = "The response is mostly grounded. Score: 9\nThe output faithfully..."
        assert parse_judge_score(text) == pytest.approx(0.9)

    def test_zero(self) -> None:
        assert parse_judge_score("Score: 0") == pytest.approx(0.0)

    def test_ten_normalized(self) -> None:
        assert parse_judge_score("Score: 10") == pytest.approx(1.0)

    def test_clamps_above_ten(self) -> None:
        assert parse_judge_score("Score: 15") == pytest.approx(1.0)

    def test_fallback_to_last_number(self) -> None:
        # No "Score:" pattern; last number is "7" (single digit, treated as raw score)
        score = parse_judge_score("This response earns a 7.")
        assert score == pytest.approx(0.7)

    def test_no_number_returns_zero(self) -> None:
        assert parse_judge_score("I cannot evaluate this.") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# build_scoring_prompt
# ---------------------------------------------------------------------------


class TestBuildScoringPrompt:
    def test_contains_query(self) -> None:
        c = _case()
        prompt = build_scoring_prompt(c)
        assert c.query in prompt

    def test_contains_candidate_output(self) -> None:
        c = _case()
        prompt = build_scoring_prompt(c)
        assert c.candidate_output in prompt

    def test_contains_context(self) -> None:
        c = _case()
        assert c.context
        prompt = build_scoring_prompt(c)
        assert c.context[0] in prompt

    def test_deterministic(self) -> None:
        c = _case()
        assert build_scoring_prompt(c) == build_scoring_prompt(c)

    def test_faithfulness_rubric_used(self) -> None:
        c = _case(metric="faithfulness")
        prompt = build_scoring_prompt(c)
        assert "grounded" in prompt.lower()

    def test_refusal_rubric_used(self) -> None:
        c = _case(metric="refusal")
        prompt = build_scoring_prompt(c)
        assert "refus" in prompt.lower()
