"""Shared fixtures for the deterministic (Tier-1) evaluation suite."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from sut.agent import AgentResponse, CoverageAgent
from sut.retriever import FixtureRetriever
from verity.cassettes import CassetteLibrary
from verity.config import Settings
from verity.cost import RunAccumulator
from verity.golden import GoldenCase, load_golden
from verity.providers import LLMProvider

if TYPE_CHECKING:
    pass

_CASSETTE_DIR = Path("datasets/cassettes")
_GOLDEN_DIR = Path("datasets/golden")


@pytest.fixture(scope="session")
def _settings() -> Settings:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Settings(cassette_mode="replay", cassette_dir=_CASSETTE_DIR)


@pytest.fixture(scope="session")
def golden_cases() -> list[GoldenCase]:
    return load_golden(_GOLDEN_DIR)


def run_case(case: GoldenCase, settings: Settings) -> AgentResponse:
    """Create a hermetic CoverageAgent for one golden case and call .answer()."""
    lib = CassetteLibrary(_CASSETTE_DIR)
    retriever = FixtureRetriever(case.id)
    accumulator = RunAccumulator()
    provider = LLMProvider(settings, accumulator, cassette_library=lib)
    agent = CoverageAgent(settings=settings, retriever=retriever, provider=provider)
    return agent.answer(case.query, member_id=case.member_id)
