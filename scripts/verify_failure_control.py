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
EXPECTED_CLASSNAME = "tests.evidence.test_failure_control"
EXPECTED_TEST_NAME = "test_expected_failure_control"


def verify(path: Path, native_exit: int) -> None:
    if isinstance(native_exit, bool) or not isinstance(native_exit, int) or native_exit != 1:
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
    cases = root.findall(".//testcase")
    if len(cases) != 1:
        raise ValueError("the control JUnit report must contain exactly one testcase")
    case = cases[0]
    if case.get("classname") != EXPECTED_CLASSNAME or case.get("name") != EXPECTED_TEST_NAME:
        raise ValueError("the control JUnit report contains an unexpected testcase")
    if case.findall("error") or case.findall("skipped"):
        raise ValueError(
            "the control testcase has an error or skip instead of the expected failure"
        )
    failures = case.findall("failure")
    if len(failures) != 1:
        raise ValueError("the control testcase must contain exactly one failure")
    messages = [failures[0].get("message", ""), "".join(failures[0].itertext())]
    if EXPECTED_MARKER not in "\n".join(messages):
        raise ValueError("the expected marker is missing from the control failure")
    if list(root.iter("error")):
        raise ValueError("the control JUnit report contains an error, including a setup failure")


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
