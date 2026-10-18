"""Tests for no-loss reconciliation of D05 Gemini run receipts."""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

from verity.calibration import CALIBRATION_METRICS
from verity.heldout_analysis import PLAN_ID
from verity.heldout_receipts import reconcile_receipts, write_reconciled_outputs


def create_dataset(path: Path) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    for metric in CALIBRATION_METRICS:
        for index in range(8):
            cases.append(
                {
                    "randomized_case_id": f"blind-{metric}-{index:02d}",
                    "metric": metric,
                    "query": f"Question {index} for {metric}?",
                    "context": f"Fictional context for {metric} case {index}.",
                    "candidate_output": f"Fictional response for {metric} case {index}.",
                }
            )
    yaml_cases = [
        {
            **case,
            "context": [case["context"]],
        }
        for case in cases
    ]
    path.write_text(yaml.safe_dump({"cases": yaml_cases}), encoding="utf-8")
    return cases


def make_receipt(
    receipt_path: Path,
    case_ids: list[str],
    dataset_hash: str,
    start_index: int = 0,
    status: str = "success",
    failed_case_ids: set[str] | None = None,
) -> None:
    failed = failed_case_ids or set()
    attempts: list[dict[str, Any]] = []
    for case_id in case_ids:
        if case_id in failed:
            attempts.append({"case_id": case_id, "status": "failed", "error_type": "HTTPError"})
        else:
            attempts.append(
                {
                    "case_id": case_id,
                    "status": "success",
                    "score": 0.8,
                    "provider_reported_cost_usd": None,
                    "response_model": "gemini-3.8-flash",
                }
            )
    receipt = {
        "schema_version": 1,
        "purpose": "bounded live D05 held-out scoring; test fixture",
        "study_plan_id": PLAN_ID,
        "dataset_sha256": dataset_hash,
        "requested_model": "gemini-3.8-flash",
        "free_project_confirmed_by_operator": True,
        "billing_plan_verified_by_api": False,
        "limits": {
            "spend_usd": 0,
            "calls": 7,
            "output_tokens_per_call": 2048,
            "output_tokens_per_run": 14336,
            "input_bytes_per_call": 16000,
            "interval_seconds": 3.1,
            "retries": 0,
        },
        "start_index": start_index,
        "selected_case_ids": case_ids,
        "attempts": attempts,
        "status": status,
        "started_at": "2026-10-18T00:00:00Z",
        "ended_at": "2026-10-18T00:01:00Z",
        "source_sha": "test-commit",
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")


class HeldoutReceiptTests(unittest.TestCase):
    def test_complete_receipts_export_exactly_one_score_per_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "heldout.yaml"
            cases = create_dataset(dataset)
            receipt_dir = root / "receipts"
            receipt_dir.mkdir()
            dataset_hash = hashlib.sha256(dataset.read_bytes()).hexdigest()
            for batch, offset in enumerate(range(0, 56, 7)):
                ids = [case["randomized_case_id"] for case in cases[offset : offset + 7]]
                make_receipt(
                    receipt_dir / f"heldout-{batch}.json",
                    ids,
                    dataset_hash,
                    start_index=offset,
                )

            rows, index = reconcile_receipts(dataset, receipt_dir)

            self.assertEqual(index["status"], "complete")
            self.assertEqual(index["successful_case_count"], 56)
            self.assertEqual(index["receipt_count"], 8)
            self.assertEqual(len(rows), 56)
            self.assertEqual(rows[0]["metric"], cases[0]["metric"])

            scores_path = root / "scores.csv"
            index_path = root / "index.json"
            written = write_reconciled_outputs(dataset, receipt_dir, scores_path, index_path)
            self.assertEqual(written["status"], "complete")
            with scores_path.open(newline="", encoding="utf-8") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 56)

    def test_failed_attempt_is_indexed_and_never_imputed_as_a_score(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "heldout.yaml"
            cases = create_dataset(dataset)
            receipt_dir = root / "receipts"
            receipt_dir.mkdir()
            dataset_hash = hashlib.sha256(dataset.read_bytes()).hexdigest()
            ids = [case["randomized_case_id"] for case in cases[:7]]
            case_id = ids[0]
            make_receipt(
                receipt_dir / "heldout-failed.json",
                ids,
                dataset_hash,
                start_index=0,
                status="failed",
                failed_case_ids={case_id},
            )

            scores_path = root / "scores.csv"
            index_path = root / "index.json"
            index = write_reconciled_outputs(dataset, receipt_dir, scores_path, index_path)

            self.assertEqual(index["status"], "incomplete")
            self.assertEqual(index["successful_case_count"], 6)
            self.assertEqual(len(index["missing_case_ids"]), 50)
            self.assertFalse(scores_path.exists())
            self.assertTrue(index_path.exists())

    def test_duplicate_success_for_case_marks_run_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "heldout.yaml"
            cases = create_dataset(dataset)
            receipt_dir = root / "receipts"
            receipt_dir.mkdir()
            dataset_hash = hashlib.sha256(dataset.read_bytes()).hexdigest()
            for batch, offset in enumerate(range(0, 56, 7)):
                ids = [case["randomized_case_id"] for case in cases[offset : offset + 7]]
                make_receipt(
                    receipt_dir / f"heldout-{batch}.json",
                    ids,
                    dataset_hash,
                    start_index=offset,
                )
            ids = [case["randomized_case_id"] for case in cases[:7]]
            first_id = ids[0]
            make_receipt(
                receipt_dir / "heldout-duplicate.json",
                ids,
                dataset_hash,
                start_index=0,
            )

            _, index = reconcile_receipts(dataset, receipt_dir)

            self.assertEqual(index["status"], "incomplete")
            self.assertEqual(
                index["duplicate_success_case_ids"],
                [case["randomized_case_id"] for case in cases[:7]],
            )

    def test_receipt_outside_frozen_call_budget_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "heldout.yaml"
            cases = create_dataset(dataset)
            receipt_dir = root / "receipts"
            receipt_dir.mkdir()
            dataset_hash = hashlib.sha256(dataset.read_bytes()).hexdigest()
            ids = [case["randomized_case_id"] for case in cases[:7]]
            make_receipt(receipt_dir / "heldout-0.json", ids, dataset_hash)
            receipt_path = receipt_dir / "heldout-0.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["limits"]["output_tokens_per_call"] = 4096
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "frozen zero-spend request bounds"):
                reconcile_receipts(dataset, receipt_dir)


if __name__ == "__main__":
    unittest.main()
