"""Tests for preparing blinded D05 reviewer label files."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

from verity.calibration import CALIBRATION_METRICS
from verity.heldout_analysis import PLAN_ID
from scripts.prepare_d05_reviewer_packets import prepare_packets


def write_dataset(path: Path) -> None:
    cases: list[dict[str, Any]] = []
    for metric in CALIBRATION_METRICS:
        for index in range(8):
            cases.append(
                {
                    "randomized_case_id": f"opaque-{metric}-{index}",
                    "metric": metric,
                    "query": f"Question {index} for {metric}?",
                    "context": [f"Fictional context for {metric} case {index}."],
                    "candidate_output": f"Fictional response for {metric} case {index}.",
                }
            )
    path.write_text(yaml.safe_dump({"cases": cases}), encoding="utf-8")


class ReviewerPacketTests(unittest.TestCase):
    def test_prepares_two_complete_blank_files_without_private_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "heldout.yaml"
            write_dataset(dataset)
            outputs = prepare_packets(dataset, root / "packets")

            self.assertEqual(len(outputs), 2)
            with outputs[0].open(newline="", encoding="utf-8") as stream:
                rows_one = list(csv.DictReader(stream))
            with outputs[1].open(newline="", encoding="utf-8") as stream:
                rows_two = list(csv.DictReader(stream))
            self.assertEqual(len(rows_one), 56)
            self.assertEqual(
                [row["randomized_case_id"] for row in rows_one],
                [row["randomized_case_id"] for row in rows_two],
            )
            self.assertTrue(all(row["plan_id"] == PLAN_ID for row in rows_one))
            self.assertTrue(all(not row["score"] and not row["pass_label"] for row in rows_one))
            self.assertFalse(any("source_family_id" in row for row in rows_one))

    def test_refuses_to_overwrite_existing_packet_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "heldout.yaml"
            write_dataset(dataset)
            output_dir = root / "packets"
            prepare_packets(dataset, output_dir)

            with self.assertRaises(FileExistsError):
                prepare_packets(dataset, output_dir)


if __name__ == "__main__":
    unittest.main()
