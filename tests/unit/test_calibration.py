"""Unit tests for the judge calibration module."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from verity.calibration import (
    CalibrationCase,
    ScoreProtocolError,
    build_scoring_prompt,
    compute_agreement,
    compute_self_bias,
    load_calibration,
    parse_judge_score,
    score_all_detailed,
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
        assert len(cases) == 56

    def test_all_ids_unique(self) -> None:
        path = Path("datasets/calibration/labeled.yaml")
        cases = load_calibration(path)
        ids = [c.id for c in cases]
        assert len(ids) == len(set(ids))

    def test_all_metrics_present(self) -> None:
        path = Path("datasets/calibration/labeled.yaml")
        cases = load_calibration(path)
        metrics = {c.metric for c in cases}
        assert metrics == {
            "completeness",
            "disambiguation",
            "refusal",
            "faithfulness",
            "hallucination",
            "answer_relevancy",
            "context_precision",
        }

    def test_eight_per_metric(self) -> None:
        path = Path("datasets/calibration/labeled.yaml")
        cases = load_calibration(path)
        for metric in (
            "completeness",
            "disambiguation",
            "refusal",
            "faithfulness",
            "hallucination",
            "answer_relevancy",
            "context_precision",
        ):
            count = sum(1 for c in cases if c.metric == metric)
            assert count == 8, f"Expected 8 cases for {metric}, got {count}"

    def test_balanced_output_families(self) -> None:
        path = Path("datasets/calibration/labeled.yaml")
        cases = load_calibration(path)
        glm = sum(1 for c in cases if c.output_family == "glm")
        other = sum(1 for c in cases if c.output_family == "other")
        assert glm == other == 28

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

    def test_allows_outer_ascii_whitespace(self) -> None:
        assert parse_judge_score(" \tScore: 7\r\n") == pytest.approx(0.7)

    def test_zero(self) -> None:
        assert parse_judge_score("Score: 0") == pytest.approx(0.0)

    def test_ten_normalized(self) -> None:
        assert parse_judge_score("Score: 10") == pytest.approx(1.0)

    @pytest.mark.parametrize(
        "text",
        [
            "Score: 100",
            "Score: -1",
            "Score: 7.5",
            "The response is grounded. Score: 9",
            "```\nScore: 9\n```",
            "Score: 9\nScore: 8",
            "Rating: 8",
            "Score: NaN",
            "",
            "   ",
            "score: 7",
            "Score:  7",
            "Score:\t7",
            "\u00a0Score: 7",
        ],
    )
    def test_rejects_every_non_contract_shape(self, text: str) -> None:
        with pytest.raises(ScoreProtocolError) as caught:
            parse_judge_score(text)
        assert not text or text not in str(caught.value)
        assert len(caught.value.diagnostic) <= 96

    def test_score_100_is_an_invalid_incomplete_measurement(self) -> None:
        class InvalidJudge:
            model_name = "test/judge"

            def generate(self, _prompt: str) -> str:
                return next(self._responses)

            def __init__(self) -> None:
                self._responses = iter(("Score: 8", "Score: 100"))

        valid_case = _case().model_copy(update={"id": "score-protocol-valid-control"})
        invalid_case = _case().model_copy(update={"id": "score-protocol-invalid-100"})
        cases = [valid_case, invalid_case]
        attempts = score_all_detailed(cases, InvalidJudge())
        assert attempts[0].score == pytest.approx(0.8)
        assert attempts[1].score is None
        assert attempts[1].invalid_reason == "score_protocol_format_mismatch:length=10"

        valid_cases = [valid_case]
        valid_scores = [0.8]
        agreement = compute_agreement(valid_cases, valid_scores)
        bias = compute_self_bias(valid_cases, valid_scores)

        from scripts.run_calibration import render_incomplete_report

        report = render_incomplete_report(
            cases, attempts, agreement, bias, "test/judge", "synthetic control"
        )
        assert "FAILURE — INCOMPLETE (1/2 valid; 1 invalid)" in report
        assert "invalid_output_count:** 1" in report
        assert "Raw agreement on valid measurements: 100.0%" in report
        assert "Score: 100" not in report
        assert "score-protocol-valid-control" in report
        assert "score-protocol-invalid-100" in report
        assert "test/judge" in report
        retained = Path("reports/calibration/score-protocol-negative-control.md").read_text(
            encoding="utf-8"
        )
        assert "score-protocol-invalid-100" in retained
        assert "score_protocol_format_mismatch:length=10" in retained
        assert "**Invalid:** 1" in retained

    def test_v1_rationales_are_rejected_and_v2_scores_are_unchanged(self) -> None:
        archive = Path("reports/calibration/archive/authored-score-v1/cassettes")
        version_two = Path("datasets/calibration/cassettes/authored-score-v2")
        manifest_path = Path("datasets/calibration/cassettes/authored-score-v2-manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["formatVersion"] == "authored-score-v2"
        assert manifest["cassetteCount"] == 112
        archived_manifest = Path(manifest["sourceArchiveManifest"])
        sidecar_path = Path(manifest["rationaleSidecar"]["path"])
        assert (
            hashlib.sha256(archived_manifest.read_bytes()).hexdigest()
            == manifest["sourceArchiveManifestSha256"]
        )
        assert (
            hashlib.sha256(sidecar_path.read_bytes()).hexdigest()
            == manifest["rationaleSidecar"]["sha256"]
        )
        old_files = sorted(archive.glob("*.json"))
        assert len(old_files) == 112
        mappings = {entry["source_v1"].split("/")[-1]: entry for entry in manifest["cassettes"]}
        for old_path in old_files:
            old_payload = json.loads(old_path.read_text(encoding="utf-8"))
            old_content = old_payload["content"]
            old_match = re.match(r"Score: (0|[1-9]|10)\n", old_content)
            assert old_match is not None
            with pytest.raises(ScoreProtocolError):
                parse_judge_score(old_content)

            new_path = version_two / old_path.name
            mapping = mappings[old_path.name]
            assert hashlib.sha256(old_path.read_bytes()).hexdigest() == mapping["source_v1_sha256"]
            assert hashlib.sha256(new_path.read_bytes()).hexdigest() == mapping["target_v2_sha256"]
            new_payload = json.loads(new_path.read_text(encoding="utf-8"))
            new_content = new_payload["content"]
            assert re.fullmatch(r"Score: (0|[1-9]|10)", new_content)
            assert parse_judge_score(new_content) == pytest.approx(int(old_match.group(1)) / 10)


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


# ---------------------------------------------------------------------------
# Calibration JSON artifact shape
# ---------------------------------------------------------------------------


class TestCalibrationJsonArtifact:
    def test_calibration_json_has_judge_metadata(self) -> None:
        import sys
        import warnings

        from scripts.run_calibration import _run_hermetic

        from verity.calibration import compute_agreement, compute_self_bias, load_calibration

        cases_path = Path("datasets/calibration/labeled.yaml")
        if not cases_path.exists():
            pytest.skip("calibration dataset not found")

        cases = load_calibration(cases_path)

        sys.path.insert(0, str(Path("scripts")))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from verity.config import Provider, Settings

            # _run_hermetic ignores the settings passed to it and always uses its
            # own internal pin (matching however the committed cassettes were
            # recorded), so this settings object only needs to be a valid,
            # env-isolated Settings instance — not a matching provider/model.
            settings = Settings(_env_file=None, provider=Provider.zai, model="glm-4.5")

        attempts = _run_hermetic(cases, settings)
        valid = [
            (case, float(attempt.score))
            for case, attempt in zip(cases, attempts, strict=True)
            if attempt.score is not None
        ]
        valid_cases = [case for case, _ in valid]
        judge_scores = [score for _, score in valid]
        agreement = compute_agreement(valid_cases, judge_scores)
        bias = compute_self_bias(valid_cases, judge_scores)

        raw: dict = {
            "judge": {
                "model": "test-model",
                "mode": "hermetic replay",
            },
            "agreement": {"n": agreement.n},
            "self_bias": {"self_preference_delta": round(bias.self_preference_delta, 4)},
            "per_case": [
                {"id": case.id, "human": case.human_score, "judge": round(score, 3)}
                for case, score in valid
            ],
        }

        assert "judge" in raw
        assert "model" in raw["judge"]
        assert "mode" in raw["judge"]

    def test_calibration_artifact_structure(self) -> None:
        import json

        artifact_dir = Path("reports/calibration")
        if not artifact_dir.exists():
            pytest.skip("no calibration artifacts present")
        json_files = list(artifact_dir.glob("calibration-*.json"))
        if not json_files:
            pytest.skip("no calibration JSON files found")
        latest = sorted(json_files)[-1]
        data = json.loads(latest.read_text())
        assert "agreement" in data
        assert "self_bias" in data
        assert "per_case" in data
