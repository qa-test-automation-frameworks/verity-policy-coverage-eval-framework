"""Predeclared, offline analysis for D05 held-out calibration labels.

This module reads already-locked human label CSVs and a separate judge-score
CSV. It makes no provider calls and never edits any input artifact.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

PLAN_ID = "D05-GEMINI-HELDOUT-2026-10-18-v1"
METRICS = (
    "answer_relevancy",
    "completeness",
    "context_precision",
    "disambiguation",
    "faithfulness",
    "hallucination",
    "refusal",
)
CASES_PER_METRIC = 8
EXPECTED_CASES = len(METRICS) * CASES_PER_METRIC
SCORE_THRESHOLD = 0.5
AGREEMENT_BAR = 0.85
MAE_BAR = 0.20
KAPPA_BAR = 0.60
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20_261_018
WILSON_Z = 1.959963984540054

LABEL_FIELDS = {
    "randomized_case_id",
    "reviewer_pseudonym",
    "metric",
    "score",
    "pass_label",
    "confidence",
    "rationale",
    "reviewed_at_utc",
}
JUDGE_FIELDS = {"randomized_case_id", "metric", "judge_score"}


@dataclass(frozen=True)
class Rating:
    """One normalized score and binary label for a blinded case."""

    case_id: str
    metric: str
    score: float
    passed: bool


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file without changing it."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        missing = required - fields
        if missing:
            raise ValueError(f"{path}: missing required columns: {', '.join(sorted(missing))}")
        rows: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path}:{line_number}: malformed or truncated CSV row")
            rows.append({key: value.strip() for key, value in row.items() if key is not None})
    return rows


def _score(value: str, path: Path, line_number: int, field: str) -> float:
    try:
        score = float(value)
    except ValueError as exc:
        raise ValueError(f"{path}:{line_number}: {field} must be a number") from exc
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError(f"{path}:{line_number}: {field} must be finite and between 0 and 1")
    return score


def load_reviewer(path: Path) -> tuple[str, dict[str, Rating]]:
    """Load one complete, consistently pseudonymized reviewer CSV."""
    rows = _read_csv(path, LABEL_FIELDS)
    if len(rows) != EXPECTED_CASES:
        raise ValueError(f"{path}: expected {EXPECTED_CASES} rows, found {len(rows)}")

    pseudonyms = {row["reviewer_pseudonym"] for row in rows}
    if len(pseudonyms) != 1 or not next(iter(pseudonyms), ""):
        raise ValueError(f"{path}: reviewer_pseudonym must be one non-empty value per file")
    pseudonym = next(iter(pseudonyms))

    ratings: dict[str, Rating] = {}
    for line_number, row in enumerate(rows, start=2):
        case_id = row["randomized_case_id"]
        metric = row["metric"]
        if not case_id:
            raise ValueError(f"{path}:{line_number}: randomized_case_id is required")
        if case_id in ratings:
            raise ValueError(f"{path}:{line_number}: duplicate case ID {case_id}")
        if metric not in METRICS:
            raise ValueError(f"{path}:{line_number}: unsupported metric {metric!r}")
        label = row["pass_label"].lower()
        if label not in {"true", "false"}:
            raise ValueError(f"{path}:{line_number}: pass_label must be true or false")
        if not row["confidence"] or not row["rationale"] or not row["reviewed_at_utc"]:
            raise ValueError(
                f"{path}:{line_number}: confidence, rationale, and timestamp are required"
            )
        score = _score(row["score"], path, line_number, "score")
        passed = label == "true"
        if passed != (score >= SCORE_THRESHOLD):
            raise ValueError(
                f"{path}:{line_number}: pass_label must match the frozen 0.5 score boundary"
            )
        ratings[case_id] = Rating(
            case_id=case_id,
            metric=metric,
            score=score,
            passed=passed,
        )

    _validate_metric_balance(ratings, path)
    return pseudonym, ratings


def load_judge_scores(path: Path) -> dict[str, Rating]:
    """Load a complete held-out judge score export keyed by randomized ID."""
    rows = _read_csv(path, JUDGE_FIELDS)
    if len(rows) != EXPECTED_CASES:
        raise ValueError(f"{path}: expected {EXPECTED_CASES} rows, found {len(rows)}")
    ratings: dict[str, Rating] = {}
    for line_number, row in enumerate(rows, start=2):
        case_id = row["randomized_case_id"]
        metric = row["metric"]
        if not case_id:
            raise ValueError(f"{path}:{line_number}: randomized_case_id is required")
        if case_id in ratings:
            raise ValueError(f"{path}:{line_number}: duplicate case ID {case_id}")
        if metric not in METRICS:
            raise ValueError(f"{path}:{line_number}: unsupported metric {metric!r}")
        score = _score(row["judge_score"], path, line_number, "judge_score")
        ratings[case_id] = Rating(
            case_id=case_id,
            metric=metric,
            score=score,
            passed=score >= SCORE_THRESHOLD,
        )
    _validate_metric_balance(ratings, path)
    return ratings


def _validate_metric_balance(ratings: dict[str, Rating], path: Path) -> None:
    counts = Counter(rating.metric for rating in ratings.values())
    if set(counts) != set(METRICS):
        raise ValueError(f"{path}: expected all seven frozen metrics, found {sorted(counts)}")
    unbalanced = {
        metric: counts[metric] for metric in METRICS if counts[metric] != CASES_PER_METRIC
    }
    if unbalanced:
        raise ValueError(f"{path}: expected {CASES_PER_METRIC} cases per metric: {unbalanced}")


def _validate_alignment(
    reviewer: dict[str, Rating], judge: dict[str, Rating], label: str
) -> list[str]:
    reviewer_ids = set(reviewer)
    judge_ids = set(judge)
    if reviewer_ids != judge_ids:
        missing = sorted(reviewer_ids - judge_ids)
        extra = sorted(judge_ids - reviewer_ids)
        raise ValueError(f"{label}: case ID mismatch; missing judge IDs={missing}, extra={extra}")
    for case_id in sorted(reviewer_ids):
        if reviewer[case_id].metric != judge[case_id].metric:
            raise ValueError(f"{label}: metric mismatch for case {case_id}")
    return sorted(reviewer_ids)


def _kappa(left: list[bool], right: list[bool]) -> float | None:
    observed = sum(a == b for a, b in zip(left, right, strict=True)) / len(left)
    left_positive = sum(left) / len(left)
    right_positive = sum(right) / len(right)
    expected = left_positive * right_positive + (1 - left_positive) * (1 - right_positive)
    if math.isclose(1.0 - expected, 0.0, abs_tol=1e-12):
        return None
    return (observed - expected) / (1.0 - expected)


def _wilson(successes: int, total: int) -> dict[str, float]:
    proportion = successes / total
    z2 = WILSON_Z**2
    denominator = 1 + z2 / total
    center = (proportion + z2 / (2 * total)) / denominator
    margin = (
        WILSON_Z
        * math.sqrt(proportion * (1 - proportion) / total + z2 / (4 * total**2))
        / denominator
    )
    return {"lower": max(0.0, center - margin), "upper": min(1.0, center + margin)}


def _percentile(sorted_values: list[float], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def _bootstrap_mae(errors: list[float], seed: int) -> dict[str, float]:
    rng = random.Random(seed)
    sample_size = len(errors)
    means = sorted(
        sum(errors[rng.randrange(sample_size)] for _ in range(sample_size)) / sample_size
        for _ in range(BOOTSTRAP_RESAMPLES)
    )
    return {"lower": _percentile(means, 0.025), "upper": _percentile(means, 0.975)}


def _classify(
    agreement: float,
    agreement_ci: dict[str, float],
    mae: float,
    mae_ci: dict[str, float],
    kappa: float | None,
) -> str:
    if agreement < AGREEMENT_BAR or mae > MAE_BAR:
        return "fail"
    if kappa is not None and kappa < KAPPA_BAR:
        return "fail"
    agreement_crosses_bar = agreement_ci["lower"] <= AGREEMENT_BAR <= agreement_ci["upper"]
    mae_crosses_bar = mae_ci["lower"] <= MAE_BAR <= mae_ci["upper"]
    if agreement_crosses_bar or mae_crosses_bar:
        return "inconclusive"
    return "pass"


def _compare(
    left: dict[str, Rating],
    right: dict[str, Rating],
    case_ids: list[str],
    seed: int,
) -> dict[str, Any]:
    matches = [left[case_id].passed == right[case_id].passed for case_id in case_ids]
    errors = [abs(left[case_id].score - right[case_id].score) for case_id in case_ids]
    agreement = sum(matches) / len(matches)
    mae = sum(errors) / len(errors)
    return {
        "n": len(case_ids),
        "raw_agreement": agreement,
        "agreement_95_wilson_ci": _wilson(sum(matches), len(matches)),
        "cohen_kappa": _kappa(
            [left[case_id].passed for case_id in case_ids],
            [right[case_id].passed for case_id in case_ids],
        ),
        "mae": mae,
        "mae_95_bootstrap_ci": _bootstrap_mae(errors, seed),
    }


def analyze(
    reviewer_one: dict[str, Rating],
    reviewer_two: dict[str, Rating],
    judge: dict[str, Rating],
    reviewer_one_pseudonym: str,
    reviewer_two_pseudonym: str,
    reviewer_one_hash: str,
    reviewer_two_hash: str,
    judge_hash: str,
    heldout_dataset_hash: str,
    manifest_hash: str,
    case_manifest: dict[str, str],
) -> dict[str, Any]:
    """Analyze two locked reviewers against one held-out judge export."""
    if reviewer_one_pseudonym == reviewer_two_pseudonym:
        raise ValueError("the two reviewer files must have distinct pseudonyms")
    reserved_pseudonyms = {"judge_scores", "heldout_dataset", "case_manifest"}
    if {reviewer_one_pseudonym, reviewer_two_pseudonym} & reserved_pseudonyms:
        raise ValueError("reviewer pseudonyms must not collide with evidence-hash keys")
    case_ids = _validate_alignment(reviewer_one, reviewer_two, "reviewer-to-reviewer")
    _validate_alignment(reviewer_one, judge, "reviewer-one-to-judge")
    _validate_alignment(reviewer_two, judge, "reviewer-two-to-judge")
    if set(case_manifest) != set(case_ids):
        raise ValueError("case manifest randomized IDs do not match reviewer and judge files")
    for case_id in case_ids:
        if case_manifest[case_id] != reviewer_one[case_id].metric:
            raise ValueError(f"case manifest metric mismatch for case {case_id}")
    if len(case_ids) != EXPECTED_CASES:
        raise ValueError(f"expected {EXPECTED_CASES} aligned cases, found {len(case_ids)}")

    per_metric: dict[str, Any] = {}
    for index, metric in enumerate(METRICS):
        metric_ids = [case_id for case_id in case_ids if reviewer_one[case_id].metric == metric]
        comparisons = {
            reviewer_one_pseudonym: _compare(
                reviewer_one, judge, metric_ids, BOOTSTRAP_SEED + index
            ),
            reviewer_two_pseudonym: _compare(
                reviewer_two, judge, metric_ids, BOOTSTRAP_SEED + index + len(METRICS)
            ),
        }
        for result in comparisons.values():
            result["decision"] = _classify(
                result["raw_agreement"],
                result["agreement_95_wilson_ci"],
                result["mae"],
                result["mae_95_bootstrap_ci"],
                result["cohen_kappa"],
            )
        per_metric[metric] = {
            "n": len(metric_ids),
            "reviewer_vs_judge": comparisons,
            "reviewer_vs_reviewer": _compare(
                reviewer_one,
                reviewer_two,
                metric_ids,
                BOOTSTRAP_SEED + index + 2 * len(METRICS),
            ),
        }

    overall_ids = case_ids
    overall = {
        reviewer_one_pseudonym: _compare(
            reviewer_one, judge, overall_ids, BOOTSTRAP_SEED + 3 * len(METRICS)
        ),
        reviewer_two_pseudonym: _compare(
            reviewer_two, judge, overall_ids, BOOTSTRAP_SEED + 3 * len(METRICS) + 1
        ),
    }
    return {
        "schema_version": 1,
        "plan_id": PLAN_ID,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "case_count": len(case_ids),
        "metrics": list(METRICS),
        "frozen_bars": {
            "score_threshold": SCORE_THRESHOLD,
            "raw_agreement_minimum": AGREEMENT_BAR,
            "mae_maximum": MAE_BAR,
            "cohen_kappa_minimum_when_meaningful": KAPPA_BAR,
            "agreement_interval": "95% Wilson",
            "mae_interval": "case-resampled percentile bootstrap 95% CI",
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "promotion_note": "An interval crossing a bar is inconclusive; retain quarantine.",
        },
        "input_sha256": {
            reviewer_one_pseudonym: reviewer_one_hash,
            reviewer_two_pseudonym: reviewer_two_hash,
            "judge_scores": judge_hash,
            "heldout_dataset": heldout_dataset_hash,
            "case_manifest": manifest_hash,
        },
        "overall_secondary_only": overall,
        "per_metric": per_metric,
    }


def _load_manifest(manifest_path: Path, dataset_path: Path) -> tuple[dict[str, str], str]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{manifest_path}: invalid JSON manifest") from exc
    if not isinstance(manifest, dict):
        raise ValueError(f"{manifest_path}: manifest root must be a JSON object")
    if manifest.get("plan_id") != PLAN_ID:
        raise ValueError(f"{manifest_path}: plan_id must be {PLAN_ID}")
    recorded_hash = manifest.get("dataset_sha256")
    actual_hash = sha256_file(dataset_path)
    if recorded_hash != actual_hash:
        raise ValueError(f"{manifest_path}: held-out dataset SHA-256 does not match manifest")
    rows = manifest.get("cases")
    if not isinstance(rows, list) or len(rows) != EXPECTED_CASES:
        raise ValueError(f"{manifest_path}: expected {EXPECTED_CASES} randomized case mappings")
    mapping: dict[str, str] = {}
    source_ids: set[str] = set()
    family_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"{manifest_path}: case mapping {index} must be an object")
        case_id = row.get("randomized_case_id")
        metric = row.get("metric")
        source_id = row.get("source_case_id")
        family_id = row.get("source_family_id")
        if (
            not isinstance(case_id, str)
            or not case_id
            or not isinstance(metric, str)
            or not metric
            or not isinstance(source_id, str)
            or not source_id
            or not isinstance(family_id, str)
            or not family_id
        ):
            raise ValueError(
                f"{manifest_path}: mapping requires randomized ID, metric, source ID and family ID"
            )
        if case_id in mapping or source_id in source_ids:
            raise ValueError(f"{manifest_path}: randomized and source case IDs must be unique")
        if metric not in METRICS:
            raise ValueError(f"{manifest_path}: unsupported metric {metric!r}")
        mapping[case_id] = metric
        source_ids.add(source_id)
        family_ids.add(family_id)
    _validate_metric_balance(
        {case_id: Rating(case_id, metric, 0.0, False) for case_id, metric in mapping.items()},
        manifest_path,
    )
    if not family_ids:
        raise ValueError(f"{manifest_path}: no source families recorded")
    try:
        dataset = yaml.safe_load(dataset_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{dataset_path}: invalid YAML held-out dataset") from exc
    if not isinstance(dataset, dict) or not isinstance(dataset.get("cases"), list):
        raise ValueError(f"{dataset_path}: expected a YAML object with a cases list")
    dataset_mapping: dict[str, str] = {}
    for index, case in enumerate(dataset["cases"]):
        if not isinstance(case, dict):
            raise ValueError(f"{dataset_path}: case {index} must be an object")
        case_id = case.get("randomized_case_id")
        metric = case.get("metric")
        if not isinstance(case_id, str) or not case_id or not isinstance(metric, str):
            raise ValueError(f"{dataset_path}: each case needs a randomized_case_id and metric")
        if case_id in dataset_mapping:
            raise ValueError(f"{dataset_path}: duplicate randomized case ID {case_id}")
        if not isinstance(case.get("query"), str) or not case["query"].strip():
            raise ValueError(f"{dataset_path}: case {case_id} needs a non-empty query")
        if (
            not isinstance(case.get("candidate_output"), str)
            or not case["candidate_output"].strip()
        ):
            raise ValueError(f"{dataset_path}: case {case_id} needs a non-empty candidate_output")
        if not isinstance(case.get("context"), list) or not all(
            isinstance(item, str) for item in case["context"]
        ):
            raise ValueError(f"{dataset_path}: case {case_id} context must be a list of strings")
        if "human_score" in case or "human_pass" in case or "rationale" in case:
            raise ValueError(
                f"{dataset_path}: human labels and rationales must be stored separately"
            )
        dataset_mapping[case_id] = metric
    if dataset_mapping != mapping:
        raise ValueError(f"{dataset_path}: case IDs/metrics do not match the private manifest")
    return mapping, actual_hash


def analyze_files(
    reviewer_one_path: Path,
    reviewer_two_path: Path,
    judge_path: Path,
    heldout_dataset_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    """Load immutable input paths, validate, and compute a redacted aggregate."""
    pseudonym_one, reviewer_one = load_reviewer(reviewer_one_path)
    pseudonym_two, reviewer_two = load_reviewer(reviewer_two_path)
    judge = load_judge_scores(judge_path)
    case_manifest, dataset_hash = _load_manifest(manifest_path, heldout_dataset_path)
    return analyze(
        reviewer_one,
        reviewer_two,
        judge,
        pseudonym_one,
        pseudonym_two,
        sha256_file(reviewer_one_path),
        sha256_file(reviewer_two_path),
        sha256_file(judge_path),
        dataset_hash,
        sha256_file(manifest_path),
        case_manifest,
    )


def write_report(report: dict[str, Any], output_path: Path) -> None:
    """Write the aggregate JSON report without modifying source artifacts."""
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite existing report: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
