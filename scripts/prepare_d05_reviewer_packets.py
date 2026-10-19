#!/usr/bin/env python3
"""Create two blank, blinded CSVs for independent D05 reviewers."""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from verity.calibration import load_heldout_calibration  # noqa: E402
from verity.heldout_analysis import PLAN_ID  # noqa: E402
from verity.metrics.rubrics import (  # noqa: E402
    ANSWER_RELEVANCY_RUBRIC,
    COMPLETENESS_RUBRIC,
    CONTEXT_PRECISION_RUBRIC,
    DISAMBIGUATION_RUBRIC,
    FAITHFULNESS_RUBRIC,
    HALLUCINATION_RUBRIC,
    REFUSAL_RUBRIC,
)

RUBRICS = {
    "answer_relevancy": ANSWER_RELEVANCY_RUBRIC,
    "completeness": COMPLETENESS_RUBRIC,
    "context_precision": CONTEXT_PRECISION_RUBRIC,
    "disambiguation": DISAMBIGUATION_RUBRIC,
    "faithfulness": FAITHFULNESS_RUBRIC,
    "hallucination": HALLUCINATION_RUBRIC,
    "refusal": REFUSAL_RUBRIC,
}

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
    """Write two blinded reviewer packets, refusing any overwrite."""
    cases = load_heldout_calibration(dataset_path)
    output_dir.mkdir(parents=True, exist_ok=False)
    outputs = []
    for packet_name in ("reviewer-one", "reviewer-two"):
        packet_dir = output_dir / packet_name
        packet_dir.mkdir()
        output = packet_dir / "labels.csv"
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
        shutil.copyfile(dataset_path, packet_dir / "heldout-dataset.yaml")
        (packet_dir / "rubrics.md").write_text(
            "# Frozen metric rubrics\n\n"
            + "\n\n---\n\n".join(
                f"## `{metric}`\n\n{rubric}" for metric, rubric in RUBRICS.items()
            )
            + "\n",
            encoding="utf-8",
        )
        (packet_dir / "instructions.md").write_text(
            f"# Independent D05 review\n\n"
            f"Study: `{PLAN_ID}`. Score each case using its metric rubric in `rubrics.md`. "
            "The rubric gives a score from 0 to 10. Convert that score to the required "
            "CSV scale from 0 to 1 by dividing by 10 (for example, rubric score 7 becomes "
            "CSV score 0.7). In `pass_label`, enter `true` for scores >= 0.5 (rubric "
            "score >= 5), otherwise `false`. Do not change case IDs or metrics.\n\n"
            "Complete every row independently. Use a stable pseudonym in every row; "
            "record confidence, a concise rationale grounded only in the supplied case, "
            "and the UTC review time. Do not discuss ratings with the other reviewer or "
            "seek authoring notes. Return only the completed `labels.csv`; keep the "
            "other reviewer's responses and any judge scores hidden until both files "
            "are submitted and locked.\n",
            encoding="utf-8",
        )
        outputs.append(output)
    return outputs[0], outputs[1]


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
    print(f"Created two blinded reviewer packets for {PLAN_ID}:")
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
