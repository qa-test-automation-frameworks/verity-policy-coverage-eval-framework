"""Tier-1: every golden case returns a structurally valid AgentResponse."""

from __future__ import annotations

from pathlib import Path

import pytest

from sut.retriever import FixtureRetriever
from tests.deterministic.conftest import run_case
from verity.checks import (
    check_citations,
    check_claim_numbers_grounded,
    check_date_expectations,
    check_human_review,
    check_must_contain,
    check_must_contain_any,
    check_must_not_contain,
    check_numeric_expectations,
    check_policy_claims_grounded,
    validate_response_schema,
)
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
    # Escalation is derived from retrieved evidence (cross-tier cost parity),
    # not from the model's own answer text, so it fires independently of
    # whether the model happens to notice or hallucinate past the anomaly.
    response = run_case(case, _settings)
    result = check_human_review(case, response)
    assert result.passed, result.message


@pytest.mark.parametrize(
    "case",
    [c for c in _CASES if c.expected_citations],
    ids=[c.id for c in _CASES if c.expected_citations],
)
def test_citations_match_expected_sources(case: GoldenCase, _settings: Settings) -> None:
    response = run_case(case, _settings)
    retrieved_chunks = FixtureRetriever(case.id).retrieve(case.query)
    retrieved_sources = [c.source for c in retrieved_chunks]
    # retrieved_chunks additionally verifies the exact section, catching a
    # citation that names a retrieved file but a section within it that was
    # not retrieved (source-file-level checking alone can't tell that apart
    # from a real hit) — resolve_citations() always draws the section from a
    # retrieved chunk, so this must still pass for every non-defect case.
    result = check_citations(
        case, response, retrieved_sources=retrieved_sources, retrieved_chunks=retrieved_chunks
    )
    if case.expects_defect:
        # A seeded defect may legitimately fail to cite the expected source —
        # that is the behavior under test, not a gate on this suite.
        return
    assert result.passed, result.message


@pytest.mark.parametrize("case", _CASES, ids=[c.id for c in _CASES])
def test_citations_never_reference_unretrieved_sources(
    case: GoldenCase, _settings: Settings
) -> None:
    """Every citation must trace back to a chunk that was actually retrieved —
    the agent must not cite sources it never saw."""
    response = run_case(case, _settings)
    retrieved_sources = {c.source for c in FixtureRetriever(case.id).retrieve(case.query)}
    cited_sources = {c.split(":")[0].strip() for c in response.citations}
    unsupported = cited_sources - retrieved_sources
    assert not unsupported, f"{case.id} cited sources never retrieved: {unsupported}"


@pytest.mark.parametrize(
    "case",
    [c for c in _CASES if c.must_contain and not c.expects_defect],
    ids=[c.id for c in _CASES if c.must_contain and not c.expects_defect],
)
def test_must_contain_tokens_present(case: GoldenCase, _settings: Settings) -> None:
    response = run_case(case, _settings)
    result = check_must_contain(case, response)
    assert result.passed, result.message


@pytest.mark.parametrize(
    "case",
    [c for c in _CASES if c.must_contain_any and not c.expects_defect],
    ids=[c.id for c in _CASES if c.must_contain_any and not c.expects_defect],
)
def test_must_contain_any_phrasing_present(case: GoldenCase, _settings: Settings) -> None:
    response = run_case(case, _settings)
    result = check_must_contain_any(case, response)
    assert result.passed, result.message


@pytest.mark.parametrize(
    "case",
    [c for c in _CASES if c.must_not_contain and not c.expects_defect],
    ids=[c.id for c in _CASES if c.must_not_contain and not c.expects_defect],
)
def test_must_not_contain_tokens_absent(case: GoldenCase, _settings: Settings) -> None:
    response = run_case(case, _settings)
    result = check_must_not_contain(case, response)
    assert result.passed, result.message


@pytest.mark.parametrize(
    "case",
    [c for c in _CASES if c.numeric_expectations and not c.expects_defect],
    ids=[c.id for c in _CASES if c.numeric_expectations and not c.expects_defect],
)
def test_numeric_expectations_satisfied(case: GoldenCase, _settings: Settings) -> None:
    response = run_case(case, _settings)
    result = check_numeric_expectations(case, response)
    assert result.passed, result.message


@pytest.mark.parametrize(
    "case",
    [c for c in _CASES if c.date_expectations and not c.expects_defect],
    ids=[c.id for c in _CASES if c.date_expectations and not c.expects_defect],
)
def test_date_expectations_satisfied(case: GoldenCase, _settings: Settings) -> None:
    response = run_case(case, _settings)
    result = check_date_expectations(case, response)
    assert result.passed, result.message


# ctrl-bronze-preventive's correct answer states "$0" as an inference from the
# retrieved chunk's "covered at 100% with no deductible" — a valid derived
# claim a lexical grounding check cannot distinguish from a fabricated
# number, since "$0" itself never appears in the chunk text. Tracked as a
# known limitation rather than silently excluded from the case set.
_LEXICAL_GROUNDING_KNOWN_LIMITATIONS = {
    "ctrl-bronze-preventive",
    "ctrl-missing-acupuncture-policy",
}

_GROUNDING_CASES = [
    c
    for c in _CASES
    if not c.expects_defect
    and c.expected_tool is None
    and c.behavior != "refuse"
    and c.id not in _LEXICAL_GROUNDING_KNOWN_LIMITATIONS
]


@pytest.mark.parametrize("case", _GROUNDING_CASES, ids=[c.id for c in _GROUNDING_CASES])
def test_claim_numbers_grounded_in_retrieved_chunks(case: GoldenCase, _settings: Settings) -> None:
    """Every number the answer states must appear in some retrieved chunk's text —
    not just that the cited source file was retrieved. Skipped for expects_defect
    cases (hallucination is the behavior under test) and expected_tool cases
    (the answer is a computed value, not a direct lookup, so it legitimately
    won't appear verbatim in retrieved text)."""
    response = run_case(case, _settings)
    chunks = FixtureRetriever(case.id).retrieve(case.query)
    result = check_claim_numbers_grounded(response, chunks)
    assert result.passed, result.message


@pytest.mark.parametrize("case", _GROUNDING_CASES, ids=[c.id for c in _GROUNDING_CASES])
def test_policy_claims_grounded_in_retrieved_chunks(case: GoldenCase, _settings: Settings) -> None:
    """Material non-numeric policy claims should be supported by retrieved context,
    not merely accompanied by a citation to a retrieved source."""
    response = run_case(case, _settings)
    chunks = FixtureRetriever(case.id).retrieve(case.query)
    result = check_policy_claims_grounded(response, chunks)
    assert result.passed, result.message
