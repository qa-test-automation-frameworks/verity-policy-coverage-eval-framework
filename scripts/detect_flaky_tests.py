"""Run a pytest selection N times and report per-test outcome variance.

CONTRIBUTING.md documents a flake policy (@pytest.mark.flaky /
@pytest.mark.quarantine) but nothing generated the evidence a maintainer
needs to decide whether a specific live test actually deserves one of those
markers. This runs the given pytest selection N times, parses each run's
JUnit XML, and flags any test whose outcome varied — passed on some runs and
failed/errored on others. It never fails the command by default; the report
is diagnostic input for a human to apply @pytest.mark.flaky/quarantine, not a
new auto-blocking gate (see T5 in the framework's own testing-strategy notes).

Usage:
    uv run python scripts/detect_flaky_tests.py --runs 5 -- tests/semantic -m live
    uv run python scripts/detect_flaky_tests.py --runs 3 --strict -- tests/deterministic
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

_DEFAULT_OUT = Path("reports/flake/flake-report.json")


def parse_junit_outcomes(xml_path: Path) -> dict[str, str]:
    """Return {node_id: outcome} for one JUnit XML file.

    outcome is one of "passed", "failed", "error", "skipped".
    """
    tree = ET.parse(xml_path)
    outcomes: dict[str, str] = {}
    for testcase in tree.getroot().iter("testcase"):
        classname = testcase.get("classname", "")
        name = testcase.get("name", "")
        node_id = f"{classname}::{name}"
        if testcase.find("failure") is not None:
            outcomes[node_id] = "failed"
        elif testcase.find("error") is not None:
            outcomes[node_id] = "error"
        elif testcase.find("skipped") is not None:
            outcomes[node_id] = "skipped"
        else:
            outcomes[node_id] = "passed"
    return outcomes


def detect_flaky(run_results: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    """Return {node_id: {"outcomes": [...], "flaky": bool}} across all runs.

    A test is flaky if it was observed both passing and failing/erroring
    across the given runs. skipped-only tests are never flagged.
    """
    all_ids: set[str] = set()
    for run in run_results:
        all_ids.update(run.keys())

    report: dict[str, dict[str, object]] = {}
    for node_id in sorted(all_ids):
        seen = [run.get(node_id, "not_run") for run in run_results]
        passed = "passed" in seen
        failed_or_errored = "failed" in seen or "error" in seen
        report[node_id] = {"outcomes": seen, "flaky": passed and failed_or_errored}
    return report


def run_n_times(runs: int, pytest_args: list[str]) -> list[dict[str, str]]:
    """Invoke pytest `runs` times against pytest_args and parse each run's outcomes."""
    results: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(runs):
            xml_path = Path(tmp) / f"run-{i}.xml"
            print(f"  Run {i + 1}/{runs}...")
            subprocess.run(
                ["uv", "run", "pytest", *pytest_args, f"--junitxml={xml_path}", "-q"],
                check=False,
            )
            results.append(parse_junit_outcomes(xml_path))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--runs", type=int, default=5, help="Number of repeated runs (default: 5)")
    parser.add_argument("--out", default=str(_DEFAULT_OUT), help="Report output path")
    parser.add_argument(
        "--strict", action="store_true", help="Exit non-zero if any flaky test is found"
    )
    parser.add_argument(
        "pytest_args", nargs=argparse.REMAINDER, help="Args passed through to pytest"
    )
    args = parser.parse_args()

    pytest_args = args.pytest_args
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    if not pytest_args:
        print("No pytest selection given — pass e.g. `-- tests/deterministic`", file=sys.stderr)
        raise SystemExit(2)

    run_results = run_n_times(args.runs, pytest_args)
    report = detect_flaky(run_results)
    flaky = {node_id: r for node_id, r in report.items() if r["flaky"]}

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"runs": args.runs, "pytest_args": pytest_args, "tests": report}, indent=2),
        encoding="utf-8",
    )
    print(f"\nWritten: {out_path}")

    if flaky:
        print(f"\n{len(flaky)} flaky test(s) detected (inconsistent pass/fail across runs):")
        for node_id, r in flaky.items():
            print(f"  - {node_id}: {r['outcomes']}")
        print(
            "\nConsider marking these @pytest.mark.flaky or @pytest.mark.quarantine "
            "per CONTRIBUTING.md's live-tier flake policy."
        )
        if args.strict:
            raise SystemExit(1)
    else:
        print("\nNo flaky tests detected across the sampled runs.")


if __name__ == "__main__":
    main()
