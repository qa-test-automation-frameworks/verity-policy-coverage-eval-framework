#!/usr/bin/env python3
"""Reconcile D05 held-out run receipts into a score CSV and immutable index."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from verity.heldout_receipts import write_reconciled_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heldout-dataset", type=Path, required=True)
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument("--scores-out", type=Path, required=True)
    parser.add_argument("--index-out", type=Path, required=True)
    args = parser.parse_args()
    try:
        index = write_reconciled_outputs(
            args.heldout_dataset,
            args.receipt_dir,
            args.scores_out,
            args.index_out,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        f"D05 receipt reconciliation {index['status']}: "
        f"{index['successful_case_count']}/{index['case_count']} unique scores"
    )
    print(f"Receipt index: {args.index_out}")
    if index["status"] == "complete":
        print(f"Judge scores: {args.scores_out}")
        return 0
    print(f"Missing cases: {len(index['missing_case_ids'])}; score CSV not written")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
