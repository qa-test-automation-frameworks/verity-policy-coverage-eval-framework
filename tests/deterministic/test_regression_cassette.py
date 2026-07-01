"""Tier-1: cassette-replay stability and manifest completeness.

These tests verify that:
1. Every golden case that makes an LLM call has a cassette (no accidental live call)
2. Re-running a case against its cassette produces the same response (replay stable)
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from sut.agent import _load_members
from sut.retriever import FixtureRetriever
from sut.tools.coverage_calculator import COVERAGE_CALCULATOR_SCHEMA
from tests.deterministic.conftest import run_case
from verity.cassettes import CassetteLibrary, request_key
from verity.config import Settings
from verity.golden import GoldenCase, load_golden

pytestmark = pytest.mark.deterministic

_GOLDEN_DIR = Path("datasets/golden")
_CASSETTE_DIR = Path("datasets/cassettes")
_ALL_CASES = load_golden(_GOLDEN_DIR)


def _requires_no_llm(case: GoldenCase) -> bool:
    """True when guardrails will short-circuit before any LLM call for this case."""
    from sut.guardrails import check_input

    refused, _ = check_input(case.query)
    return refused


def _first_turn_key(case: GoldenCase, settings: Settings) -> str:
    from sut.agent import _build_system_prompt

    members = _load_members()
    member = members[case.member_id]
    retriever = FixtureRetriever(case.id)
    chunks = retriever.retrieve(case.query)
    system_prompt = _build_system_prompt(member, chunks)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": case.query},
    ]
    tools = [COVERAGE_CALCULATOR_SCHEMA]
    litellm_model, _, _ = settings.resolved_provider()
    return request_key(litellm_model, messages, tools, settings.temperature, settings.max_tokens)


@pytest.fixture(scope="session")
def replay_settings() -> Settings:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Settings(cassette_mode="replay", cassette_dir=_CASSETTE_DIR)


class TestCassetteManifest:
    def test_all_llm_cases_have_cassettes(self, replay_settings: Settings) -> None:
        """Every case that makes an LLM call must have a pre-recorded cassette."""
        lib = CassetteLibrary(_CASSETTE_DIR)
        missing: list[str] = []
        for case in _ALL_CASES:
            if _requires_no_llm(case):
                continue  # guardrail refusal; no LLM call, no cassette needed
            key = _first_turn_key(case, replay_settings)
            if not lib.has(key):
                missing.append(f"{case.id} (key={key[:12]}…)")
        assert not missing, (
            f"Missing cassettes for cases: {missing}. Run 'make record' to regenerate."
        )

    def test_cassette_dir_has_json_files(self) -> None:
        jsons = list(_CASSETTE_DIR.glob("*.json"))
        assert jsons, f"No cassette JSON files found in {_CASSETTE_DIR}"

    def test_retrieval_dir_has_all_fixture_files(self) -> None:
        fixture_dir = _CASSETTE_DIR / "retrieval"
        missing = [c.id for c in _ALL_CASES if not (fixture_dir / f"{c.id}.json").exists()]
        assert not missing, f"Missing retrieval fixture files: {missing}"


class TestCassetteReplayStability:
    @pytest.mark.parametrize(
        "case",
        [c for c in _ALL_CASES if not _requires_no_llm(c)],
        ids=[c.id for c in _ALL_CASES if not _requires_no_llm(c)],
    )
    def test_replay_is_deterministic(self, case: GoldenCase, replay_settings: Settings) -> None:
        """Running the same case twice must return the same answer text."""
        resp1 = run_case(case, replay_settings)
        resp2 = run_case(case, replay_settings)
        assert resp1.answer == resp2.answer, (
            f"Non-deterministic replay for {case.id!r}: answers differ between runs"
        )
