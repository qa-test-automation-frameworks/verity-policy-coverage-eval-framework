"""Tier-1: every golden case returns a structurally valid AgentResponse."""

from __future__ import annotations

from pathlib import Path

import pytest

from sut.retriever import FixtureRetriever
from tests.deterministic.conftest import run_case
from verity.checks import check_citations, check_human_review, validate_response_schema
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


@pytest.mark.parametrize("case", _CASES, ids=[c.id for c in _CASES])
def test_human_review_signal_matches_case(case: GoldenCase, _settings: Settings) -> None:
    response = run_case(case, _settings)
    result = check_human_review(case, response)
    if case.expects_defect and case.requires_human_review:
        assert not result.passed, "Expected human-review defect to be caught"
    else:
        assert result.passed, result.message


@pytest.mark.parametrize(
    "case",
    [c for c in _CASES if c.expected_citations],
    ids=[c.id for c in _CASES if c.expected_citations],
)
def test_citations_match_expected_sources(case: GoldenCase, _settings: Settings) -> None:
    response = run_case(case, _settings)
    retrieved_sources = [c.source for c in FixtureRetriever(case.id).retrieve(case.query)]
    result = check_citations(case, response, retrieved_sources=retrieved_sources)
    if case.expects_defect:
        # A seeded defect may legitimately fail to cite the expected source —
        # that is the behavior under test, not a gate on this suite.
        return
    assert result.passed, result.message


@pytest.mark.parametrize("case", _CASES, ids=[c.id for c in _CASES])
def test_citations_never_reference_unretrieved_sources(case: GoldenCase, _settings: Settings) -> None:
    """Every citation must trace back to a chunk that was actually retrieved —
    the agent must not cite sources it never saw."""
    response = run_case(case, _settings)
    retrieved_sources = {c.source for c in FixtureRetriever(case.id).retrieve(case.query)}
    cited_sources = {c.split(":")[0].strip() for c in response.citations}
    unsupported = cited_sources - retrieved_sources
    assert not unsupported, f"{case.id} cited sources never retrieved: {unsupported}"
