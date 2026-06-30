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
from verity.reporting import render_cost_summary, write_step_summary

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


_SESSION_ACCUMULATOR = RunAccumulator()


def run_probe(probe: AdversarialProbe, settings: Settings) -> AgentResponse:
    """Run a single adversarial probe through the hermetic agent."""
    lib = CassetteLibrary(_ADV_CASSETTE_DIR)
    retriever = FixtureRetriever(probe.effective_fixture_id())
    provider = LLMProvider(settings, _SESSION_ACCUMULATOR, cassette_library=lib)
    agent = CoverageAgent(settings=settings, retriever=retriever, provider=provider)
    return agent.answer(probe.prompt, member_id=probe.member_id)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    summary = render_cost_summary(_SESSION_ACCUMULATOR)
    write_step_summary(summary)
