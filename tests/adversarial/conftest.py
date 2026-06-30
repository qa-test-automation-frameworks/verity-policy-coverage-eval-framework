"""Shared fixtures for the adversarial (Tier-3) evaluation suite."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from sut.agent import AgentResponse, CoverageAgent
from sut.retriever import FixtureRetriever
from verity.adversarial import AdversarialProbe, load_probes
from verity.cassettes import CassetteLibrary
from verity.config import Settings
from verity.cost import RunAccumulator
from verity.providers import LLMProvider

_ADV_CASSETTE_DIR = Path("datasets/adversarial/cassettes")
_PROBES_PATH = Path("datasets/adversarial/probes.yaml")


@pytest.fixture(scope="session")
def _settings() -> Settings:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Settings(cassette_mode="replay", cassette_dir=_ADV_CASSETTE_DIR)


@pytest.fixture(scope="session")
def probes() -> list[AdversarialProbe]:
    return load_probes(_PROBES_PATH)


def run_probe(probe: AdversarialProbe, settings: Settings) -> AgentResponse:
    """Run a single adversarial probe through the hermetic agent."""
    lib = CassetteLibrary(_ADV_CASSETTE_DIR)
    retriever = FixtureRetriever(probe.effective_fixture_id())
    accumulator = RunAccumulator()
    provider = LLMProvider(settings, accumulator, cassette_library=lib)
    agent = CoverageAgent(settings=settings, retriever=retriever, provider=provider)
    return agent.answer(probe.prompt, member_id=probe.member_id)
