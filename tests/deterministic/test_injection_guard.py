"""Tier-1: prompt-injection compliance detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.deterministic.conftest import run_case
from verity.checks import check_injection, check_must_not_contain
from verity.config import Settings
from verity.golden import GoldenCase, load_golden

pytestmark = pytest.mark.deterministic

_ALL_CASES = load_golden(Path("datasets/golden"))

# Clean cases — response must not echo injection language
_CLEAN_ANSWER_CASES = [c for c in _ALL_CASES if not c.expects_defect and c.behavior == "answer"]

# Defect #7 — injection compliance in response (defect detected when check fails)
_DEFECT_INJECTION_CASES = [c for c in _ALL_CASES if c.expects_defect and c.defect_id == 7]


@pytest.mark.parametrize("case", _CLEAN_ANSWER_CASES, ids=[c.id for c in _CLEAN_ANSWER_CASES])
def test_clean_responses_no_injection_compliance(case: GoldenCase, _settings: Settings) -> None:
    """Control cases must not contain injection-compliance markers."""
    response = run_case(case, _settings)
    result = check_injection(response)
    assert result.passed, result.message


@pytest.mark.parametrize("case", _DEFECT_INJECTION_CASES, ids=[c.id for c in _DEFECT_INJECTION_CASES])
def test_defect_injection_compliance_detected(case: GoldenCase, _settings: Settings) -> None:
    """Defect #7: response complies with §A5 injection — injection check must fail (defect detected)."""
    response = run_case(case, _settings)
    result = check_injection(response)
    assert not result.passed, (
        f"Expected defect #{case.defect_id} to be detected by injection check for {case.id!r}, "
        f"but check passed (no injection language found in response)"
    )


@pytest.mark.parametrize("case", _DEFECT_INJECTION_CASES, ids=[c.id for c in _DEFECT_INJECTION_CASES])
def test_defect_injection_must_not_contain(case: GoldenCase, _settings: Settings) -> None:
    """Defect #7: must_not_contain tokens confirm injection-compliance language is present."""
    if not case.must_not_contain:
        pytest.skip("No must_not_contain tokens for this case")
    response = run_case(case, _settings)
    result = check_must_not_contain(case, response)
    # Defect cases: must_not_contain check FAILING = forbidden token found = defect detected
    assert not result.passed, (
        f"Expected forbidden injection tokens to be found in response for {case.id!r}"
    )
