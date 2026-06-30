"""Tier-1: every golden case returns a structurally valid AgentResponse."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.deterministic.conftest import run_case
from verity.checks import validate_response_schema
from verity.config import Settings
from verity.golden import GoldenCase, load_golden

pytestmark = pytest.mark.deterministic

_CASES = load_golden(Path("datasets/golden"))


@pytest.mark.parametrize("case", _CASES, ids=[c.id for c in _CASES])
def test_response_schema(case: GoldenCase, _settings: Settings) -> None:
    response = run_case(case, _settings)
    result = validate_response_schema(response)
    assert result.passed, result.message


@pytest.mark.parametrize("case", _CASES, ids=[c.id for c in _CASES])
def test_citations_are_strings(case: GoldenCase, _settings: Settings) -> None:
    response = run_case(case, _settings)
    assert all(isinstance(c, str) for c in response.citations), (
        f"Non-string citation in {case.id}: {response.citations}"
    )


@pytest.mark.parametrize("case", _CASES, ids=[c.id for c in _CASES])
def test_token_counts_non_negative(case: GoldenCase, _settings: Settings) -> None:
    response = run_case(case, _settings)
    assert response.prompt_tokens >= 0
    assert response.completion_tokens >= 0
    assert response.total_tokens >= 0
