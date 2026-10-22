#!/usr/bin/env python3
"""Prepare two blinded label packets for a frozen runtime-adapter cohort."""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from verity.runtime_adapter_calibration import load_dataset  # noqa: E402

LABEL_FIELDS = (
    "dataset_sha256",
    "case_id",
    "adapter_key",
    "pair_id",
    "reviewer_pseudonym",
    "label",
    "confidence",
    "rationale",
    "reviewed_at_utc",
)


def prepare_packets(dataset_path: Path, output_dir: Path) -> tuple[Path, Path]:
    dataset = load_dataset(dataset_path)
    if dataset.cohort_kind != "independently-labeled-heldout":
        raise ValueError("review packets can only be prepared for a held-out cohort")
    output_dir.mkdir(parents=True, exist_ok=False)
    outputs: list[Path] = []
    for packet_name in ("reviewer-one", "reviewer-two"):
        packet_dir = output_dir / packet_name
        packet_dir.mkdir()
        labels_path = packet_dir / "labels.csv"
        with labels_path.open("x", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=LABEL_FIELDS)
            writer.writeheader()
            for case in dataset.cases:
                writer.writerow(
                    {
                        "dataset_sha256": dataset.sha256,
                        "case_id": case.case_id,
                        "adapter_key": case.adapter_key,
                        "pair_id": case.pair_id,
                        "reviewer_pseudonym": "",
                        "label": "",
                        "confidence": "",
                        "rationale": "",
                        "reviewed_at_utc": "",
                    }
                )
        shutil.copyfile(dataset_path, packet_dir / "heldout-dataset.yaml")
        (packet_dir / "instructions.md").write_text(
            "# Independent runtime-adapter label packet\n\n"
            f"Dataset SHA-256: `{dataset.sha256}`\n\n"
            "Review each candidate response as `good` only when it satisfies the frozen "
            "case context and expected behavior; otherwise label it `bad`. Record a "
            "confidence value, short rationale, one stable reviewer pseudonym, and UTC "
            "review time for every row. Treat the paired answers independently. Do not "
            "discuss labels with the other reviewer or view any adapter scores before "
            "both files are complete and hashed. Return the filled CSV unchanged apart "
            "from the blank review fields.\n"
        )
        outputs.append(labels_path)
    return outputs[0], outputs[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    first, second = prepare_packets(args.dataset, args.out)
    print("Created two independent reviewer packets:")
    print(first)
    print(second)
    print("Complete and hash both label files before running any adapter judge.")


if __name__ == "__main__":
    main()
