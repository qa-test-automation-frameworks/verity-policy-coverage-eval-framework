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
            "Set the provider key matching VERITY_PROVIDER in .env "
            "(for example VERITY_ZAI_API_KEY)",
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
_SEMANTIC_MEASUREMENTS: dict[str, dict[str, object]] = {}
_NODE_FAILURE_DETAILS: dict[str, str] = {}


def record_defect_measurement(
    case: GoldenCase,
    *,
    metric: str,
    score: float,
    threshold: float,
    threshold_passed: bool,
) -> None:
    """Record whether a seeded defect reproduced under the current live model/judge pairing.

    A defect not reproducing means the model no longer exhibits the authored
    failure mode for this metric -- a fact about model quality, not a bug in
    the checking code or a control-case regression. Recording that outcome as
    xfail (rather than a hard failure) keeps this tier's pass/fail signal
    reserved for detector errors and control-case drift; the NOT_REPRODUCED/
    VERIFIED status itself is still captured in full for defects_report.py.
    """
    status = "NOT_REPRODUCED" if threshold_passed else "VERIFIED"
    measurement_key = f"{case.id}::{metric}"
    _SEMANTIC_MEASUREMENTS[measurement_key] = {
        "case_id": case.id,
        "defect_id": case.defect_id,
        "metric": metric,
        "score": score,
        "threshold": threshold,
        "threshold_passed": threshold_passed,
        "status": status,
    }
    if threshold_passed:
        pytest.xfail(
            f"Seeded behavior for {case.id!r} did not reproduce under the current "
            f"model/judge pairing ({metric} threshold {threshold}, got {score:.3f})"
        )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, None]:
    outcome = yield
    if call.when == "call":
        report = outcome.get_result()
        _NODE_RESULTS[item.nodeid] = report.outcome
        if report.failed:
            _NODE_FAILURE_DETAILS[item.nodeid] = str(report.longrepr)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    summary = render_cost_summary(_SESSION_ACCUMULATOR)
    write_step_summary(summary)
    if _NODE_RESULTS:
        out = Path("reports/semantic/results.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "outcomes": _NODE_RESULTS,
            "measurements": _SEMANTIC_MEASUREMENTS,
            "failure_details": _NODE_FAILURE_DETAILS,
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        record = compute_trend_record(
            "semantic", _NODE_RESULTS, _SESSION_ACCUMULATOR, latency_budget_ms=LIVE_BUDGET_MS
        )
        append_trend(record)
