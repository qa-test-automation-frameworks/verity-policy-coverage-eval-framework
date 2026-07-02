"""Shared fixtures for the semantic (Tier-2) evaluation suite.

ALL tests here are marked `semantic` and `live` -- they make real LLM calls
via the configured provider and are NOT run in the PR gate (see pr-gate.yml).

Run with: make eval-semantic  (requires API key in .env)
"""

from __future__ import annotations

import json
import os
import warnings
from collections.abc import Generator
from pathlib import Path

import pytest

from sut.agent import CoverageAgent
from sut.retriever import PolicyRetriever
from verity.config import Settings
from verity.cost import RunAccumulator
from verity.golden import GoldenCase, load_golden
from verity.judges import ProviderJudge
from verity.latency import LIVE_BUDGET_MS
from verity.providers import LLMProvider
from verity.reporting import render_cost_summary, write_step_summary
from verity.trends import append_trend, compute_trend_record

pytestmark = [pytest.mark.semantic, pytest.mark.live]

_GOLDEN_DIR = Path("datasets/golden")


def _require_api_key() -> None:
    """Skip the entire session if no API key is configured."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s = Settings()
    _, _, key = s.resolved_provider()
    if key is None:
        pytest.skip(
            "No API key configured for semantic eval. "
            "Set VERITY_ZAI_API_KEY, VERITY_OPENROUTER_API_KEY, "
            "or VERITY_TOGETHER_API_KEY in .env",
            allow_module_level=True,
        )


# Guard at import time so all tests in the suite are skipped when no key is set
_require_api_key()

# Disable deepeval telemetry
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")
os.environ.setdefault("DEEPEVAL_ERROR_REPORTING_OPT_OUT", "1")


@pytest.fixture(scope="session")
def settings() -> Settings:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Settings()


@pytest.fixture(scope="session")
def judge(settings: Settings) -> ProviderJudge:
    return ProviderJudge(settings=settings)


@pytest.fixture(scope="session")
def golden_cases() -> list[GoldenCase]:
    return load_golden(_GOLDEN_DIR)


_SESSION_ACCUMULATOR = RunAccumulator()


def live_agent(settings: Settings) -> CoverageAgent:
    """Create a live CoverageAgent using the real retriever (needs Chroma indexed)."""
    provider = LLMProvider(settings, _SESSION_ACCUMULATOR)
    retriever = PolicyRetriever(settings.retrieval)
    return CoverageAgent(settings=settings, retriever=retriever, provider=provider)


_NODE_RESULTS: dict[str, str] = {}


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, None]:
    outcome = yield
    if call.when == "call":
        _NODE_RESULTS[item.nodeid] = outcome.get_result().outcome


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    summary = render_cost_summary(_SESSION_ACCUMULATOR)
    write_step_summary(summary)
    if _NODE_RESULTS:
        out = Path("reports/semantic/results.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(_NODE_RESULTS, indent=2), encoding="utf-8")

        record = compute_trend_record(
            "semantic", _NODE_RESULTS, _SESSION_ACCUMULATOR, latency_budget_ms=LIVE_BUDGET_MS
        )
        append_trend(record)
