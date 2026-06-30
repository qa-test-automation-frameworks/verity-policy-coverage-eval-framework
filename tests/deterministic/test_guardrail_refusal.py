"""Tier-1: refusal and answer-behavior checks for all golden cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.deterministic.conftest import run_case
from verity.checks import check_refusal
from verity.config import Settings
from verity.golden import GoldenCase, load_golden

pytestmark = pytest.mark.deterministic

_ALL_CASES = load_golden(Path("datasets/golden"))

# Cases where we expect correct refusal behavior (controls and defect that *should* refuse)
_REFUSAL_CASES = [c for c in _ALL_CASES if c.behavior == "refuse" and not c.expects_defect]

# Defect #6: query bypasses guardrail — refusal expected but not delivered
_DEFECT_REFUSAL_CASES = [c for c in _ALL_CASES if c.expects_defect and c.behavior == "refuse"]

# Cases where answer is expected (should NOT be refused)
_ANSWER_CASES = [c for c in _ALL_CASES if c.behavior == "answer" and not c.expects_defect]


@pytest.mark.parametrize("case", _REFUSAL_CASES, ids=[c.id for c in _REFUSAL_CASES])
def test_correct_refusals(case: GoldenCase, _settings: Settings) -> None:
    """Clean refusal cases must be refused (guardrail fires as expected)."""
    response = run_case(case, _settings)
    result = check_refusal(case, response)
    assert result.passed, result.message


@pytest.mark.parametrize("case", _ANSWER_CASES, ids=[c.id for c in _ANSWER_CASES])
def test_no_spurious_refusals(case: GoldenCase, _settings: Settings) -> None:
    """Control cases that expect an answer must not be refused."""
    response = run_case(case, _settings)
    result = check_refusal(case, response)
    assert result.passed, result.message


@pytest.mark.parametrize("case", _DEFECT_REFUSAL_CASES, ids=[c.id for c in _DEFECT_REFUSAL_CASES])
def test_defect_refusal_breach_detected(case: GoldenCase, _settings: Settings) -> None:
    """Defect #6: the query bypasses the guardrail — refusal check must FAIL."""
    response = run_case(case, _settings)
    result = check_refusal(case, response)
    # For a defect case, the check FAILING means the defect is detected (passing assertion)
    assert not result.passed, (
        f"Expected defect #{case.defect_id} to be detected by refusal check for {case.id!r}, "
        f"but the check passed (refused={response.refused})"
    )
