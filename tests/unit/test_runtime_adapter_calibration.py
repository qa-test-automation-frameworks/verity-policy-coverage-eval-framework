"""Offline contract tests for the runtime-adapter calibration protocol."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from verity.runtime_adapter_calibration import (
    ADAPTERS,
    MeasurementAttempt,
    analyze_adapter_calibration,
    authored_control_labels,
    build_registry,
    load_dataset,
    load_reviewer_labels,
    resolve_heldout_labels,
    wilson_interval,
    _promotion_status,
)


def test_authored_controls_are_separate_and_versioned() -> None:
    dataset = load_dataset(
        Path("datasets/calibration/runtime-adapters/authored-controls-v1.yaml")
    )
    assert dataset.cohort_kind == "authored-control"
    assert len(dataset.cases) == 14
    assert {case.adapter_key for case in dataset.cases} == set(ADAPTERS)
    assert all(case.control_truth is not None for case in dataset.cases)


def test_wilson_interval_explains_empty_class_denominator() -> None:
    interval = wilson_interval(0, 0, "no valid labeled bad cases")
    assert interval == {
        "lower": None,
        "upper": None,
        "successes": 0,
        "denominator": 0,
        "denominator_reason": "no valid labeled bad cases",
    }


def test_invalid_case_stays_in_completeness_not_confusion_matrix() -> None:
    dataset = load_dataset(
        Path("datasets/calibration/runtime-adapters/authored-controls-v1.yaml")
    )
    labels = authored_control_labels(dataset)
    attempts = [
        MeasurementAttempt(
            case.case_id,
            "invalid",
            invalid_reason="adapter_error:ProtocolError",
        )
        if case.case_id == "ra-ar-7f31-b"
        else MeasurementAttempt(
            case.case_id,
            "completed",
            raw_score=0.95 if case.control_truth == "good" else 0.05,
        )
        for case in dataset.cases
    ]
    registry = build_registry(
        source_sha="a" * 40,
        working_tree_clean=False,
        judge_config={"provider": "synthetic", "model": "fake"},
    )

    report = analyze_adapter_calibration(dataset, labels, attempts, registry)
    answer_relevancy = report["per_adapter"]["answer_relevancy"]
    assert report["status"] == "synthetic-adapter-control"
    assert answer_relevancy["completeness"] == {
        "planned": 2,
        "attempted": 2,
        "completed": 1,
        "invalid": 1,
        "not_attempted": 0,
        "complete": False,
    }
    matrix = answer_relevancy["confusion_matrix_valid_measurements_only"]
    assert matrix["tp"] == 0
    assert matrix["fn"] == 0
    assert matrix["valid_labeled_bad_denominator"] == 0
    assert answer_relevancy["sensitivity"] is None
    assert answer_relevancy["sensitivity_wilson_95"]["denominator_reason"] == (
        "no valid labeled bad cases"
    )
    assert answer_relevancy["promotion_status"] == "not applicable to synthetic controls"


def test_adapter_polarity_uses_the_frozen_threshold_and_handles_adverse_scores() -> None:
    dataset = load_dataset(
        Path("datasets/calibration/runtime-adapters/authored-controls-v1.yaml")
    )
    labels = authored_control_labels(dataset)
    attempts = []
    for case in dataset.cases:
        if case.adapter_key == "answer_relevancy":
            # Deliberately reverse this adapter's authored-control outcomes.
            score = 0.05 if case.control_truth == "good" else 0.95
        elif case.adapter_key == "completeness":
            # A score exactly on the threshold remains a good decision.
            score = 0.70 if case.control_truth == "good" else 0.699
        else:
            score = 0.95 if case.control_truth == "good" else 0.05
        attempts.append(MeasurementAttempt(case.case_id, "completed", raw_score=score))
    registry = build_registry(
        source_sha="a" * 40,
        working_tree_clean=False,
        judge_config={"provider": "synthetic", "model": "fake"},
    )

    report = analyze_adapter_calibration(dataset, labels, attempts, registry)
    adverse = report["per_adapter"]["answer_relevancy"]
    assert adverse["sensitivity"] == 0.0
    assert adverse["specificity"] == 0.0
    assert adverse["confusion_matrix_valid_measurements_only"]["fn"] == 1
    assert adverse["confusion_matrix_valid_measurements_only"]["fp"] == 1

    thresholded = report["per_adapter"]["completeness"]
    assert thresholded["sensitivity"] == 1.0
    assert thresholded["specificity"] == 1.0
    assert thresholded["raw_agreement"] == 1.0
    assert thresholded["promotion_status"] == "not applicable to synthetic controls"


def test_small_perfect_heldout_samples_remain_insufficient_for_promotion() -> None:
    eight_case_interval = wilson_interval(8, 8, "no valid labeled cases")

    status = _promotion_status(
        invalid=0,
        not_attempted=0,
        sensitivity=1.0,
        specificity=1.0,
        sensitivity_interval=eight_case_interval,
        specificity_interval=eight_case_interval,
    )

    assert status == "insufficient evidence: Wilson lower bound below predeclared bar"


def test_one_class_confounded_adapter_is_not_rescued_by_other_adapters() -> None:
    dataset = load_dataset(
        Path("datasets/calibration/runtime-adapters/authored-controls-v1.yaml")
    )
    labels = authored_control_labels(dataset)
    for case in dataset.cases:
        if case.adapter_key == "answer_relevancy":
            labels[case.case_id]["label"] = "good"
    attempts = [
        MeasurementAttempt(
            case.case_id,
            "completed",
            raw_score=0.95 if case.control_truth == "good" else 0.05,
        )
        for case in dataset.cases
    ]
    registry = build_registry(
        source_sha="a" * 40,
        working_tree_clean=False,
        judge_config={"provider": "synthetic", "model": "fake"},
    )

    report = analyze_adapter_calibration(dataset, labels, attempts, registry)
    confounded = report["per_adapter"]["answer_relevancy"]
    assert confounded["sensitivity"] is None
    assert confounded["sensitivity_wilson_95"]["denominator_reason"] == (
        "no valid labeled bad cases"
    )
    assert confounded["specificity"] == 0.5
    assert report["per_adapter"]["completeness"]["sensitivity"] == 1.0


@pytest.mark.parametrize("disposition", ["duplicate", "missing"])
def test_measurement_ids_must_match_the_frozen_dataset(disposition: str) -> None:
    dataset = load_dataset(
        Path("datasets/calibration/runtime-adapters/authored-controls-v1.yaml")
    )
    labels = authored_control_labels(dataset)
    attempts = [
        MeasurementAttempt(
            case.case_id,
            "completed",
            raw_score=0.95 if case.control_truth == "good" else 0.05,
        )
        for case in dataset.cases
    ]
    if disposition == "duplicate":
        attempts[-1] = attempts[0]
    else:
        attempts.pop()
    registry = build_registry(
        source_sha="a" * 40,
        working_tree_clean=False,
        judge_config={"provider": "synthetic", "model": "fake"},
    )

    with pytest.raises(ValueError, match="one measurement disposition"):
        analyze_adapter_calibration(dataset, labels, attempts, registry)


def test_heldout_labels_require_independent_receipts_and_adjudication(tmp_path: Path) -> None:
    dataset_path = tmp_path / "heldout.yaml"
    dataset_path.write_text(
        "schema_version: runtime-adapter-calibration-v1\n"
        "cohort_id: heldout-test-v1\n"
        "cohort_kind: independently-labeled-heldout\n"
        "source_kind: independently-labeled-heldout\n"
        "cases:\n"
        "  - case_id: case-a\n"
        "    pair_id: pair-1\n"
        "    adapter_key: completeness\n"
        "    pair_slot: a\n"
        "    input: Summarize both benefits.\n"
        "    context: [Benefit A and Benefit B.]\n"
        "    expected_output: Both benefits are covered.\n"
        "    candidate_output: Both benefits are covered.\n"
        "  - case_id: case-b\n"
        "    pair_id: pair-1\n"
        "    adapter_key: completeness\n"
        "    pair_slot: b\n"
        "    input: Summarize both benefits.\n"
        "    context: [Benefit A and Benefit B.]\n"
        "    expected_output: Both benefits are covered.\n"
        "    candidate_output: Only Benefit A is covered.\n",
        encoding="utf-8",
    )
    dataset = load_dataset(dataset_path)
    fields = [
        "dataset_sha256",
        "case_id",
        "adapter_key",
        "pair_id",
        "reviewer_pseudonym",
        "label",
        "confidence",
        "rationale",
        "reviewed_at_utc",
    ]

    def write_labels(
        path: Path,
        reviewer: str,
        second_label: str,
        dataset_hash: str | None = None,
    ) -> None:
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for case_id, label in (("case-a", "good"), ("case-b", second_label)):
                writer.writerow(
                    {
                        "dataset_sha256": dataset_hash or dataset.sha256,
                        "case_id": case_id,
                        "adapter_key": "completeness",
                        "pair_id": "pair-1",
                        "reviewer_pseudonym": reviewer,
                        "label": label,
                        "confidence": "high",
                        "rationale": "Reviewed independently against frozen context.",
                        "reviewed_at_utc": "2026-10-22T00:00:00Z",
                    }
                )

    one_path = tmp_path / "reviewer-one.csv"
    two_path = tmp_path / "reviewer-two.csv"
    write_labels(one_path, "reviewer-a", "bad")
    write_labels(two_path, "reviewer-b", "good")
    adjudication_path = tmp_path / "adjudication.csv"
    with adjudication_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "dataset_sha256",
                "case_id",
                "adjudicator_id",
                "label",
                "rationale",
                "reviewed_at_utc",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "dataset_sha256": dataset.sha256,
                "case_id": "case-b",
                "adjudicator_id": "reviewer-c",
                "label": "bad",
                "rationale": "The answer omits the second benefit.",
                "reviewed_at_utc": "2026-10-22T00:00:00Z",
            }
        )

    labels = resolve_heldout_labels(
        dataset,
        load_reviewer_labels(one_path, dataset),
        load_reviewer_labels(two_path, dataset),
        adjudication_path,
    )
    assert labels["case-b"]["label"] == "bad"
    assert labels["case-b"]["adjudication"]["adjudicator_id"] == "reviewer-c"
    assert labels["case-a"]["label"] == "good"

    with pytest.raises(ValueError, match="distinct pseudonyms"):
        resolve_heldout_labels(
            dataset,
            load_reviewer_labels(one_path, dataset),
            load_reviewer_labels(one_path, dataset),
            adjudication_path,
        )

    mismatched_path = tmp_path / "mismatched-receipt.csv"
    write_labels(mismatched_path, "reviewer-d", "bad", dataset_hash="b" * 64)
    with pytest.raises(ValueError, match="dataset hash does not match"):
        load_reviewer_labels(mismatched_path, dataset)
