"""Tier-1: tool-argument checks for golden cases with expected_tool set."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.deterministic.conftest import run_case
from verity.checks import check_tool_args
from verity.config import Settings
from verity.golden import GoldenCase, load_golden

pytestmark = pytest.mark.deterministic

_ALL_CASES = load_golden(Path("datasets/golden"))

# Cases that should call the tool correctly (clean cases with expected_tool)
_CLEAN_TOOL_CASES = [c for c in _ALL_CASES if c.expected_tool is not None and not c.expects_defect]

# Defect cases that should fail tool-arg checks (#3, #5)
_DEFECT_TOOL_CASES = [c for c in _ALL_CASES if c.expected_tool is not None and c.expects_defect]


@pytest.mark.parametrize("case", _CLEAN_TOOL_CASES, ids=[c.id for c in _CLEAN_TOOL_CASES])
def test_clean_tool_args_pass(case: GoldenCase, _settings: Settings) -> None:
    """Clean cases with expected_tool should call the tool with correct arguments."""
    response = run_case(case, _settings)
    result = check_tool_args(case, response)
    assert result.passed, result.message


@pytest.mark.parametrize("case", _DEFECT_TOOL_CASES, ids=[c.id for c in _DEFECT_TOOL_CASES])
def test_defect_tool_arg_detected(case: GoldenCase, _settings: Settings) -> None:
    """Defect cases with expected_tool should fail tool-arg checks (defect detected)."""
    response = run_case(case, _settings)
    result = check_tool_args(case, response)
    assert not result.passed, (
        f"Expected defect #{case.defect_id} to be detected by tool-arg check for {case.id!r}, "
        f"but the check passed unexpectedly"
    )
