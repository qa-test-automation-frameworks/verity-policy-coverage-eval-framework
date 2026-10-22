#!/usr/bin/env python3
"""Compare stable numbers in the committed report with the score-only replay."""

from __future__ import annotations

import argparse
from pathlib import Path


def report_fingerprint(path: Path) -> dict[str, list[str]]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    overall = [
        line
        for line in lines
        if line.startswith((
            "| Raw agreement |",
            "| Cohen's kappa |",
            "| MAE (0-1 scale) |",
            "| N |",
        ))
    ]
    per_metric = [
        line
        for line in lines
        if line.startswith((
            "| answer_relevancy |",
            "| completeness |",
            "| context_precision |",
            "| disambiguation |",
            "| faithfulness |",
            "| hallucination |",
            "| refusal |",
        ))
    ]
    self_bias = [
        line
        for line in lines
        if line.startswith((
            "| GLM (own family) |",
            "| Other family |",
            "| **Self-preference delta** |",
        ))
    ]
    case_scores = [line for line in lines if line.startswith("| `calib-")]
    return {
        "overall": overall,
        "per_metric": per_metric,
        "self_bias": self_bias,
        "case_scores": case_scores,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("committed_report", type=Path)
    parser.add_argument("replayed_report", type=Path)
    args = parser.parse_args()
    committed = report_fingerprint(args.committed_report)
    replayed = report_fingerprint(args.replayed_report)
    if committed != replayed:
        differing = [key for key in committed if committed[key] != replayed[key]]
        raise SystemExit(
            "score-only authored cassette replay changed committed report figures: "
            + ", ".join(differing)
        )
    if len(committed["overall"]) != 4 or len(committed["per_metric"]) != 7:
        raise SystemExit("committed report is missing an expected overall or per-metric result")
    if len(committed["case_scores"]) != 56:
        raise SystemExit("committed report must retain all 56 authored case score rows")
    print("Score-only replay matches the committed synthetic report numbers and case rows.")


if __name__ == "__main__":
    main()
