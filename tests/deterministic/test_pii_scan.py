"""Tier-1: PII leakage detection for golden cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from sut.agent import _load_members
from tests.deterministic.conftest import run_case
from verity.checks import check_pii
from verity.config import Settings
from verity.golden import GoldenCase, load_golden

pytestmark = pytest.mark.deterministic

_ALL_CASES = load_golden(Path("datasets/golden"))
_MEMBERS = _load_members()

# Clean answer cases — PII must not appear in response
_CLEAN_ANSWER_CASES = [c for c in _ALL_CASES if not c.expects_defect and c.behavior == "answer"]

# Defect #8 cases — PII WILL appear (defect detected)
_DEFECT_PII_CASES = [c for c in _ALL_CASES if c.expects_defect and c.defect_id == 8]


def _member_name(case: GoldenCase) -> str:
    return str(_MEMBERS.get(case.member_id, {}).get("name", ""))


@pytest.mark.parametrize("case", _CLEAN_ANSWER_CASES, ids=[c.id for c in _CLEAN_ANSWER_CASES])
def test_clean_responses_no_pii(case: GoldenCase, _settings: Settings) -> None:
    """Control answer cases must not leak PII (name, DOB, member-ID) in response text."""
    response = run_case(case, _settings)
    result = check_pii(response, member_name=_member_name(case))
    assert result.passed, result.message


@pytest.mark.parametrize("case", _DEFECT_PII_CASES, ids=[c.id for c in _DEFECT_PII_CASES])
def test_defect_pii_leakage_detected(case: GoldenCase, _settings: Settings) -> None:
    """Defect #8: response echoes member name / DOB — PII check must fail (defect detected)."""
    response = run_case(case, _settings)
    result = check_pii(response, member_name=_member_name(case))
    assert not result.passed, (
        f"Expected defect #{case.defect_id} to be detected by PII check for {case.id!r}, "
        f"but check passed (no PII found)"
    )
