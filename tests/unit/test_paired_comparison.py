"""Offline controls for compatible, paired model-comparison cohorts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from verity.golden import load_golden
from verity.paired_comparison import analyze_paired_comparison, evaluate_golden_response

_ROOT = Path(__file__).resolve().parents[2]


def _records(
    count: int,
    *,
    baseline_correct: bool = True,
    challenger_correct: bool = True,
    source_kind: str = "authored_control",
    baseline_cost: float | None = None,
    challenger_cost: float | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    baseline: list[dict[str, Any]] = []
    challenger: list[dict[str, Any]] = []
    for index in range(count):
        case_id = f"case-{index:02d}"
        input_hash = hashlib.sha256(case_id.encode()).hexdigest()
        shared = {
            "schema_version": 1,
            "cohort_hash": "a" * 64,
            "case_id": case_id,
            "input_hash": input_hash,
            "oracle_version": "oracle-v1",
            "measurement_status": "valid",
            "input_tokens": None,
            "output_tokens": None,
            "latency_ms": None,
            "source_kind": source_kind,
        }
        baseline.append(
            {
                **shared,
                "candidate_id": "baseline",
                "correct": baseline_correct,
                "critical_failure": False,
                "cost_usd": baseline_cost,
                "config_id": "baseline-config",
                "source_id": "source-v1",
            }
        )
        challenger.append(
            {
                **shared,
                "candidate_id": "challenger",
                "correct": challenger_correct,
                "critical_failure": False,
                "cost_usd": challenger_cost,
                "config_id": "challenger-config",
                "source_id": "source-v1",
            }
        )
    return baseline, challenger


def test_equal_cohort_is_paired_by_case_id() -> None:
    baseline, challenger = _records(30)

    report = analyze_paired_comparison(baseline, list(reversed(challenger)))

    assert report["input_valid"] is True
    assert report["quality"]["ties"] == 30
    assert report["quality"]["paired_mean_delta"] == 0
    assert report["decision"] == "candidate"


def test_strictly_worse_challenger_favors_the_baseline() -> None:
    baseline, challenger = _records(30, baseline_correct=True, challenger_correct=False)

    report = analyze_paired_comparison(baseline, challenger)

    assert report["quality"]["losses"] == 30
    assert report["quality"]["bootstrap_95_percentile_interval"] == [-1.0, -1.0]
    assert report["decision"] == "baseline"


def test_strictly_better_challenger_is_candidate() -> None:
    baseline, challenger = _records(30, baseline_correct=False, challenger_correct=True)

    report = analyze_paired_comparison(baseline, challenger)

    assert report["quality"]["wins"] == 30
    assert report["decision"] == "candidate"


def test_missing_cost_is_unknown_and_authored_cost_cannot_support_savings() -> None:
    baseline, challenger = _records(30, baseline_cost=None, challenger_cost=None)

    report = analyze_paired_comparison(baseline, challenger)

    assert report["cost"]["paired_cost_count"] == 0
    assert report["cost"]["challenger_mean_usd"] is None
    assert report["cost"]["cost_saving_supported"] is False


def test_invalid_measurements_do_not_contribute_cost_or_latency_deltas() -> None:
    baseline, challenger = _records(
        30,
        source_kind="live",
        baseline_cost=1.0,
        challenger_cost=0.5,
    )
    baseline[0]["measurement_status"] = "invalid"
    baseline[0]["correct"] = None

    report = analyze_paired_comparison(baseline, challenger)

    assert report["cost"]["paired_cost_count"] == 29
    assert report["cost"]["cost_saving_supported"] is False
    assert report["case_outcomes"][0]["cost_delta_usd"] is None


def test_duplicates_and_one_sided_cases_are_reported_not_silently_dropped() -> None:
    baseline, challenger = _records(3)
    baseline.append(dict(baseline[0]))
    challenger.pop()

    report = analyze_paired_comparison(baseline, challenger)
    codes = {item["code"] for item in report["diagnostics"]}

    assert "duplicate_case_id" in codes
    assert "one_sided_case" in codes
    assert report["decision"] == "inconclusive"


def test_cohort_and_oracle_mismatches_are_rejected() -> None:
    baseline, challenger = _records(30)
    challenger[0]["cohort_hash"] = "c" * 64
    challenger[1]["oracle_version"] = "oracle-v2"

    report = analyze_paired_comparison(baseline, challenger)
    codes = {item["code"] for item in report["diagnostics"]}

    assert "mixed_identity" in codes
    assert "pair_identity_mismatch" in codes
    assert report["decision"] == "inconclusive"


def test_candidate_identity_collision_makes_decision_inconclusive() -> None:
    baseline, challenger = _records(30)
    for record in challenger:
        record["candidate_id"] = "baseline"

    report = analyze_paired_comparison(baseline, challenger)

    assert report["input_valid"] is False
    assert "candidate_id_collision" in {item["code"] for item in report["diagnostics"]}
    assert report["decision"] == "inconclusive"


def test_critical_challenger_failure_cannot_be_overruled_by_lower_cost() -> None:
    baseline, challenger = _records(
        30,
        baseline_correct=True,
        challenger_correct=False,
        source_kind="live",
        baseline_cost=1.0,
        challenger_cost=0.5,
    )
    challenger[0]["critical_failure"] = True

    report = analyze_paired_comparison(baseline, challenger)

    assert report["cost"]["cost_saving_supported"] is True
    assert report["decision"] == "reject"


def test_fewer_than_thirty_independent_pairs_is_inconclusive() -> None:
    baseline, challenger = _records(1, baseline_correct=False, challenger_correct=True)

    report = analyze_paired_comparison(baseline, challenger)

    assert report["quality"]["wins"] == 1
    assert report["decision"] == "inconclusive"


def test_flipping_the_authored_stale_answer_reverses_oracle_outcome() -> None:
    case = next(
        item
        for item in load_golden(_ROOT / "datasets/golden")
        if item.id == "defect-2-silver-premium-stale"
    )
    cited_chunk = SimpleNamespace(source="amendments.md", section="§A1")
    correct_response = SimpleNamespace(
        answer="The amended Silver plan monthly premium is $445 effective 2024-07-01.",
        refused=False,
        citations=["amendments.md: §A1"],
        retrieved_chunks=[cited_chunk],
    )
    stale_response = SimpleNamespace(
        answer="The current Silver plan monthly premium is $420.",
        refused=False,
        citations=["amendments.md: §A1"],
        retrieved_chunks=[cited_chunk],
    )

    assert evaluate_golden_response(case, correct_response) == (True, False, [])
    stale_correct, stale_critical, failures = evaluate_golden_response(case, stale_response)
    assert stale_correct is False
    assert stale_critical is True
    assert "temporal_amount" in failures
