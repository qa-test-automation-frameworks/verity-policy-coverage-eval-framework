"""Verify the recorded raw failure as an independent required pytest result."""

from pathlib import Path

import pytest
from scripts.verify_failure_control import verify

pytestmark = pytest.mark.evidence_control

RAW_JUNIT = Path("reports/evidence/native/failure-control.xml")
RAW_NATIVE_EXIT = Path("reports/evidence/native/failure-control-exit.txt")


def test_recorded_failure_control_verdict() -> None:
    raw_exit_text = RAW_NATIVE_EXIT.read_text(encoding="utf-8").strip()
    if not raw_exit_text.isascii() or not raw_exit_text.isdigit():
        raise ValueError("the recorded raw native exit must be a non-negative integer")
    verify(RAW_JUNIT, int(raw_exit_text))
