"""Shared fixtures for the deterministic (Tier-1) evaluation suite."""

from __future__ import annotations

import os
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

# Session-wide accumulator purely for latency/cost trend tracking in single-process pytest runs.
# xdist workers keep separate process-local copies; do not treat the trend file as an
# exact aggregate when this tier is sharded. Each run_case() call also uses its own
# fresh accumulator so per-response usage stays correctly scoped.
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
            sut_profile="seeded",
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


def run_case_capturing_conversations(
    case: GoldenCase, settings: Settings
) -> tuple[AgentResponse, list[list[dict]]]:
    """Like run_case, but also returns every messages list sent to provider.complete().

    Lets a test assert structural properties (role ordering, tool_call_id
    matching) of the exact conversation the real agent constructed for a
    replayed golden case, not just its final answer.
    """
    lib = CassetteLibrary(_CASSETTE_DIR)
    retriever = FixtureRetriever(case.id)
    accumulator = RunAccumulator()
    provider = LLMProvider(settings, accumulator, cassette_library=lib)

    captured: list[list[dict]] = []
    original_complete = provider.complete

    def _capturing_complete(*args: object, **kwargs: object) -> object:
        messages = kwargs.get("messages")
        if messages is not None:
            captured.append(list(messages))  # type: ignore[arg-type]
        return original_complete(*args, **kwargs)  # type: ignore[arg-type]

    provider.complete = _capturing_complete  # type: ignore[method-assign]

    agent = CoverageAgent(settings=settings, retriever=retriever, provider=provider)
    response = agent.answer(case.query, member_id=case.member_id)
    _SESSION_ACCUMULATOR.records.extend(accumulator.records)
    return response, captured


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, None]:
    outcome = yield
    if call.when == "call":
        _NODE_RESULTS[item.nodeid] = outcome.get_result().outcome


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if os.environ.get("PYTEST_XDIST_WORKER") or not _NODE_RESULTS:
        return
    record = compute_trend_record(
        "deterministic",
        _NODE_RESULTS,
        _SESSION_ACCUMULATOR,
        latency_budget_ms=DETERMINISTIC_BUDGET_MS,
    )
    append_trend(record)
