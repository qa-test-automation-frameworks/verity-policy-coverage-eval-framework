"""Verify the intentional pytest failure is the sole reported testcase failure."""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from .evidence import parse_junit
except ImportError:
    from evidence import parse_junit

EXPECTED_MARKER = "VERITY_EVIDENCE_CONTROL_FAILURE"


def verify(path: Path, native_exit: int) -> None:
    if native_exit != 1:
        raise ValueError(f"expected the control pytest process to exit 1; got {native_exit}")
    report = parse_junit(path)
    if report.get("state") != "complete":
        raise ValueError(
            f"control JUnit report is not complete: {report.get('reason', report.get('state'))}"
        )
    counts = report["counts"]
    if counts != {
        "unit": "test_case",
        "selected": 1,
        "executed": 1,
        "passed": 0,
        "failed": 1,
        "skipped": 0,
        "retried": 0,
        "semantics": (
            "JUnit testcase invocations; selected includes skips; errors count as failures."
        ),
    }:
        raise ValueError(f"control did not produce exactly one failed testcase: {counts}")
    root = ET.parse(path).getroot()
    messages = [node.text or "" for node in root.iter() if node.tag in {"failure", "error"}]
    if len(messages) != 1 or EXPECTED_MARKER not in messages[0]:
        raise ValueError("the failed testcase did not contain the expected negative-control marker")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--native-exit", type=int, required=True)
    args = parser.parse_args()
    verify(args.junit, args.native_exit)
    print("Confirmed exactly one intended pytest failure and a complete native JUnit record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
