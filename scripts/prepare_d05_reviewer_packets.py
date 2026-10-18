#!/usr/bin/env python3
"""Create two blank, blinded CSVs for independent D05 reviewers."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from verity.calibration import load_heldout_calibration  # noqa: E402
from verity.heldout_analysis import PLAN_ID  # noqa: E402

FIELDNAMES = (
    "plan_id",
    "randomized_case_id",
    "reviewer_pseudonym",
    "metric",
    "score",
    "pass_label",
    "confidence",
    "rationale",
    "reviewed_at_utc",
)


def prepare_packets(dataset_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """Write two independent blank label files, refusing any overwrite."""
    cases = load_heldout_calibration(dataset_path)
    output_dir.mkdir(parents=True, exist_ok=False)
    outputs = (output_dir / "reviewer-one.csv", output_dir / "reviewer-two.csv")
    for output in outputs:
        with output.open("x", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
            writer.writeheader()
            for case in cases:
                writer.writerow(
                    {
                        "plan_id": PLAN_ID,
                        "randomized_case_id": case.randomized_case_id,
                        "reviewer_pseudonym": "",
                        "metric": case.metric,
                        "score": "",
                        "pass_label": "",
                        "confidence": "",
                        "rationale": "",
                        "reviewed_at_utc": "",
                    }
                )
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--heldout-dataset",
        type=Path,
        default=_ROOT / "datasets/calibration/heldout-d05.yaml",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="new local directory; the tool refuses to overwrite an existing directory",
    )
    args = parser.parse_args()
    try:
        outputs = prepare_packets(args.heldout_dataset, args.out_dir)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Created two blank blinded review files for {PLAN_ID}:")
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
