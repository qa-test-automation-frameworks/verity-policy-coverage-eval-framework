"""Shared fixtures for the deterministic (Tier-1) evaluation suite."""

from __future__ import annotations

import warnings
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from sut.agent import AgentResponse, CoverageAgent
from sut.retriever import FixtureRetriever
from verity.cassettes import CassetteLibrary
from verity.config import Provider, Settings
from verity.cost import RunAccumulator
from verity.golden import GoldenCase, load_golden
from verity.latency import DETERMINISTIC_BUDGET_MS
from verity.providers import LLMProvider
from verity.trends import append_trend, compute_trend_record

if TYPE_CHECKING:
    pass

_CASSETTE_DIR = Path("datasets/cassettes")
_GOLDEN_DIR = Path("datasets/golden")

# Session-wide accumulator purely for latency/cost trend tracking — each
# run_case() call also uses its own fresh accumulator so per-response usage
# stays correctly scoped (see verity.cost.RunAccumulator.usage_and_cost_since).
_SESSION_ACCUMULATOR = RunAccumulator()
_NODE_RESULTS: dict[str, str] = {}


@pytest.fixture(scope="session")
def _settings() -> Settings:
    # Isolated from any local .env and pinned to the provider/model the
    # committed cassettes were recorded against, so Tier-1 replays identically
    # regardless of what a developer has configured for live runs.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Settings(
            _env_file=None,
            provider=Provider.zai,
            model="glm-4.5",
            cassette_mode="replay",
            cassette_dir=_CASSETTE_DIR,
        )


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
    response = agent.answer(case.query, member_id=case.member_id)
    _SESSION_ACCUMULATOR.records.extend(accumulator.records)
    return response


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, None]:
    outcome = yield
    if call.when == "call":
        _NODE_RESULTS[item.nodeid] = outcome.get_result().outcome


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not _NODE_RESULTS:
        return
    record = compute_trend_record(
        "deterministic",
        _NODE_RESULTS,
        _SESSION_ACCUMULATOR,
        latency_budget_ms=DETERMINISTIC_BUDGET_MS,
    )
    append_trend(record)
