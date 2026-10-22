#!/usr/bin/env python3
"""Analyze locked D05 reviewer labels against held-out Gemini judge scores."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from subprocess import CalledProcessError, run

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from verity.heldout_analysis import analyze_files, sha256_file, write_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewer-one", type=Path, required=True, help="locked reviewer CSV")
    parser.add_argument("--reviewer-two", type=Path, required=True, help="locked reviewer CSV")
    parser.add_argument("--judge-scores", type=Path, required=True, help="held-out judge score CSV")
    parser.add_argument(
        "--heldout-dataset", type=Path, required=True, help="frozen held-out case file"
    )
    parser.add_argument(
        "--case-manifest",
        type=Path,
        required=True,
        help="private randomized-ID/provenance manifest",
    )
    parser.add_argument("--output", type=Path, required=True, help="aggregate JSON report path")
    args = parser.parse_args()

    try:
        report = analyze_files(
            args.reviewer_one,
            args.reviewer_two,
            args.judge_scores,
            args.heldout_dataset,
            args.case_manifest,
        )
        report["analysis_commit"] = run(
            ["git", "rev-parse", "HEAD"],
            cwd=_ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
        report["analysis_code_sha256"] = {
            "module": sha256_file(_ROOT / "src/verity/heldout_analysis.py"),
            "cli": sha256_file(Path(__file__).resolve()),
        }
        write_report(report, args.output)
    except (OSError, ValueError, CalledProcessError) as exc:
        parser.error(str(exc))
    print(f"D05 held-out analysis written to {args.output}")
    print(
        f"Cases: {report['case_count']}; metrics: {len(report['metrics'])}; "
        f"plan: {report['plan_id']}"
    )
    for metric, details in report["per_metric"].items():
        decisions = ", ".join(
            f"{reviewer}: {summary['decision']}"
            for reviewer, summary in details["reviewer_vs_judge"].items()
        )
        print(f"{metric}: {decisions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
