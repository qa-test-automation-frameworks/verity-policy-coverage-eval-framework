"""Tests for the offline, predeclared D05 held-out analysis."""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from verity.heldout_analysis import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    METRICS,
    Rating,
    _bootstrap_mae,
    _classify,
    _kappa,
    _load_manifest,
    _wilson,
    analyze,
    load_reviewer,
    write_report,
)


class HeldoutAnalysisTests(unittest.TestCase):
    def test_wilson_interval_is_bounded_and_includes_threshold_for_eight_of_eight(self) -> None:
        interval = _wilson(8, 8)

        self.assertGreaterEqual(interval["lower"], 0.0)
        self.assertLessEqual(interval["upper"], 1.0)
        self.assertLess(interval["lower"], 0.85)
        self.assertGreaterEqual(interval["upper"], 0.85)

    def test_kappa_is_undefined_for_degenerate_marginals(self) -> None:
        self.assertIsNone(_kappa([True, True], [True, True]))
        self.assertEqual(_kappa([True, False], [True, False]), 1.0)

    def test_bootstrap_mae_is_repeatable_for_frozen_seed(self) -> None:
        errors = [0.0, 0.1, 0.2, 0.3]

        self.assertEqual(
            _bootstrap_mae(errors, BOOTSTRAP_SEED),
            _bootstrap_mae(errors, BOOTSTRAP_SEED),
        )
        self.assertEqual(BOOTSTRAP_RESAMPLES, 10_000)

    def test_point_pass_with_interval_crossing_bar_is_inconclusive(self) -> None:
        agreement_ci = {"lower": 0.67, "upper": 1.0}
        mae_ci = {"lower": 0.0, "upper": 0.1}

        self.assertEqual(_classify(1.0, agreement_ci, 0.0, mae_ci, None), "inconclusive")

    def test_interval_touching_bar_is_inconclusive(self) -> None:
        agreement_ci = {"lower": 0.85, "upper": 0.95}
        mae_ci = {"lower": 0.0, "upper": 0.2}

        self.assertEqual(_classify(0.9, agreement_ci, 0.1, mae_ci, 0.7), "inconclusive")

    def test_full_balanced_case_set_reports_each_metric_and_keeps_small_sample_inconclusive(
        self,
    ) -> None:
        reviewer_one: dict[str, Rating] = {}
        reviewer_two: dict[str, Rating] = {}
        judge: dict[str, Rating] = {}
        for metric in METRICS:
            for number in range(8):
                case_id = f"blind-{metric}-{number:02d}"
                rating = Rating(case_id, metric, 0.9, True)
                reviewer_one[case_id] = rating
                reviewer_two[case_id] = rating
                judge[case_id] = rating

        report = analyze(
            reviewer_one,
            reviewer_two,
            judge,
            "reviewer-a",
            "reviewer-b",
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "d" * 64,
            "e" * 64,
            {case_id: rating.metric for case_id, rating in reviewer_one.items()},
        )

        self.assertEqual(report["case_count"], 56)
        self.assertEqual(set(report["per_metric"]), set(METRICS))
        for metric_result in report["per_metric"].values():
            self.assertEqual(metric_result["n"], 8)
            self.assertEqual(metric_result["reviewer_vs_judge"]["reviewer-a"]["raw_agreement"], 1.0)
            self.assertEqual(
                metric_result["reviewer_vs_judge"]["reviewer-a"]["decision"], "inconclusive"
            )

    def test_reviewer_label_must_follow_frozen_score_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviewer.csv"
            fields = [
                "randomized_case_id",
                "reviewer_pseudonym",
                "metric",
                "score",
                "pass_label",
                "confidence",
                "rationale",
                "reviewed_at_utc",
            ]
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for metric in METRICS:
                    for number in range(8):
                        writer.writerow(
                            {
                                "randomized_case_id": f"blind-{metric}-{number:02d}",
                                "reviewer_pseudonym": "reviewer-a",
                                "metric": metric,
                                "score": "0.4",
                                "pass_label": "true",
                                "confidence": "high",
                                "rationale": "test fixture",
                                "reviewed_at_utc": "2026-10-18T00:00:00Z",
                            }
                        )

            with self.assertRaisesRegex(ValueError, "frozen 0.5 score boundary"):
                load_reviewer(path)

    def test_report_writer_refuses_to_overwrite_prior_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.json"
            path.write_text("prior report\n", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                write_report({"schema_version": 1}, path)

            self.assertEqual(path.read_text(encoding="utf-8"), "prior report\n")

    def test_private_manifest_must_hash_and_match_unlabeled_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_path = root / "heldout.yaml"
            manifest_path = root / "manifest.json"
            cases = []
            manifest_cases = []
            for metric in METRICS:
                for number in range(8):
                    case_id = f"blind-{metric}-{number:02d}"
                    cases.append(
                        {
                            "randomized_case_id": case_id,
                            "metric": metric,
                            "query": "A fictional coverage question?",
                            "context": ["Fictional source passage."],
                            "candidate_output": "A fictional candidate response.",
                        }
                    )
                    manifest_cases.append(
                        {
                            "randomized_case_id": case_id,
                            "source_case_id": f"source-{metric}-{number:02d}",
                            "source_family_id": f"family-{metric}-{number:02d}",
                            "metric": metric,
                        }
                    )
            dataset_path.write_text(yaml.safe_dump({"cases": cases}), encoding="utf-8")
            manifest = {
                "plan_id": "D05-GEMINI-HELDOUT-2026-10-18-v1",
                "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
                "cases": manifest_cases,
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            mapping, dataset_hash = _load_manifest(manifest_path, dataset_path)

            self.assertEqual(len(mapping), 56)
            self.assertEqual(dataset_hash, manifest["dataset_sha256"])
            dataset_path.write_text(dataset_path.read_text(encoding="utf-8") + "# changed\n")
            with self.assertRaisesRegex(ValueError, "SHA-256 does not match"):
                _load_manifest(manifest_path, dataset_path)


if __name__ == "__main__":
    unittest.main()
