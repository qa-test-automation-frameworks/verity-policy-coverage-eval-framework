"""Tier-1: assert that seeded defects #5-#8 are caught by deterministic checks.

Each test in this module runs a defect case through its corresponding check and
asserts that the check FAILS — confirming the defect is detected. The test
passes when the defect is reliably caught.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sut.agent import _load_members
from tests.deterministic.conftest import run_case
from verity.checks import (
    check_injection,
    check_must_not_contain,
    check_pii,
    check_refusal,
    check_tool_args,
)
from verity.config import Settings
from verity.golden import GoldenCase, load_golden

pytestmark = pytest.mark.deterministic

_ALL_CASES = load_golden(Path("datasets/golden"))
_MEMBERS = _load_members()


def _by_defect(defect_id: int) -> GoldenCase:
    matches = [c for c in _ALL_CASES if c.defect_id == defect_id]
    assert matches, f"No golden case found for defect #{defect_id}"
    return matches[0]


class TestDefect5ToolArgTransposition:
    """Defect #5: coverage_calculator not called or called with wrong args."""

    def test_tool_arg_check_fails(self, _settings: Settings) -> None:
        case = _by_defect(5)
        response = run_case(case, _settings)
        result = check_tool_args(case, response)
        assert not result.passed, (
            "Defect #5 not detected: tool-arg check unexpectedly passed "
            f"(tool_invocations={[ti.tool_name for ti in response.tool_invocations]})"
        )

    def test_defect_is_expects_defect_flag(self) -> None:
        assert _by_defect(5).expects_defect is True


class TestDefect6RefusalBreach:
    """Defect #6: query bypasses guardrail and is answered instead of refused."""

    def test_refusal_check_fails(self, _settings: Settings) -> None:
        case = _by_defect(6)
        response = run_case(case, _settings)
        result = check_refusal(case, response)
        assert not result.passed, (
            "Defect #6 not detected: refusal check unexpectedly passed "
            f"(refused={response.refused})"
        )

    def test_response_is_not_refused(self, _settings: Settings) -> None:
        case = _by_defect(6)
        response = run_case(case, _settings)
        assert not response.refused, (
            "Defect #6 not triggered: guardrail caught the query (defect may be fixed)"
        )


class TestDefect7PromptInjection:
    """Defect #7: agent echoes injection-compliance language from §A5."""

    def test_injection_check_fails(self, _settings: Settings) -> None:
        case = _by_defect(7)
        response = run_case(case, _settings)
        result = check_injection(response)
        assert not result.passed, (
            "Defect #7 not detected: injection check unexpectedly passed. "
            f"Answer: {response.answer[:200]!r}"
        )

    def test_must_not_contain_fails(self, _settings: Settings) -> None:
        case = _by_defect(7)
        if not case.must_not_contain:
            pytest.skip("No must_not_contain tokens for defect #7 case")
        response = run_case(case, _settings)
        result = check_must_not_contain(case, response)
        assert not result.passed, "Defect #7: forbidden injection tokens not found in response"


class TestDefect8PiiLeakage:
    """Defect #8: member PII (name, DOB) appears in response text."""

    def test_pii_check_fails(self, _settings: Settings) -> None:
        case = _by_defect(8)
        member_name = str(_MEMBERS.get(case.member_id, {}).get("name", ""))
        response = run_case(case, _settings)
        result = check_pii(response, member_name=member_name)
        assert not result.passed, (
            "Defect #8 not detected: PII check unexpectedly passed. "
            f"Answer: {response.answer[:200]!r}"
        )

    def test_must_not_contain_fails(self, _settings: Settings) -> None:
        case = _by_defect(8)
        if not case.must_not_contain:
            pytest.skip("No must_not_contain tokens for defect #8 case")
        response = run_case(case, _settings)
        result = check_must_not_contain(case, response)
        assert not result.passed, "Defect #8: forbidden PII tokens not found in response"


class TestDefectCaughtSummary:
    """Summary test: print which defects are caught and which are clean controls."""

    def test_defects_5_to_8_all_caught(self, _settings: Settings) -> None:
        results: list[str] = []
        caught: list[int] = []
        missed: list[int] = []

        for defect_id, check_fn, check_label in [
            (5, lambda case, resp: check_tool_args(case, resp), "tool_args"),
            (6, lambda case, resp: check_refusal(case, resp), "refusal"),
            (7, lambda case, resp: check_injection(resp), "injection"),
            (
                8,
                lambda case, resp: check_pii(
                    resp, member_name=str(_MEMBERS.get(case.member_id, {}).get("name", ""))
                ),
                "pii",
            ),
        ]:
            case = _by_defect(defect_id)
            response = run_case(case, _settings)
            cr = check_fn(case, response)  # type: ignore[operator]
            detected = not cr.passed
            status = "CAUGHT" if detected else "MISSED"
            results.append(f"  Defect #{defect_id} ({case.id}): {status} by {check_label} check")
            (caught if detected else missed).append(defect_id)

        print("\n\n=== Deterministic Tier — Defect Detection Summary ===")
        for line in results:
            print(line)
        print(f"\nCaught: {caught}  Missed: {missed}")

        assert not missed, f"Defects not caught by deterministic checks: {missed}"
