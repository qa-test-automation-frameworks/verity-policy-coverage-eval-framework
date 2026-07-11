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
from dataclasses import asdict
from pathlib import Path

import pytest

from sut.agent import AgentResponse, CoverageAgent
from sut.retriever import Chunk, PolicyRetriever
from verity.config import Settings
from verity.cost import RunAccumulator
from verity.golden import GoldenCase, load_golden
from verity.judges import ProviderJudge
from verity.latency import LIVE_BUDGET_MS
from verity.providers import LLMProvider
from verity.reporting import render_cost_summary, write_step_summary
from verity.statistics import StatResult, pass_rate_wilson_interval
from verity.trends import append_trend, compute_trend_record
from scripts.dataset_inventory import inventory

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
    # Pinned to the seeded profile regardless of the configured default: the
    # seeded-defect golden cases and their ground truth assume the seeded
    # agent behavior (defects #5/#6/#8), so a "clean" default must not
    # silently change what this suite measures.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Settings(sut_profile="seeded")


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


def _chunk_evidence(chunks: list[Chunk]) -> list[dict[str, object]]:
    return [
        {
            "source": chunk.source,
            "section": chunk.section,
            "chunk_id": chunk.chunk_id,
            "rank": chunk.rank,
            "score": chunk.score,
            "corpus_fingerprint": chunk.corpus_fingerprint,
        }
        for chunk in chunks
    ]


def _response_evidence(response: AgentResponse | None) -> dict[str, object]:
    if response is None:
        return {}
    return {
        "trace_id": response.trace_id,
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
        "total_tokens": response.total_tokens,
        "estimated_cost_usd": response.estimated_cost_usd,
    }


def wilson_interval_payload(stat: StatResult) -> dict[str, float] | None:
    if stat.n <= 1:
        return None
    lower, upper = pass_rate_wilson_interval(stat)
    return {"lower": lower, "upper": upper, "confidence_z": 1.96}


def wilson_interval_message(stat: StatResult) -> str:
    interval = wilson_interval_payload(stat)
    if interval is None:
        return ""
    return f" Wilson 95% pass-rate interval=[{interval['lower']:.3f}, {interval['upper']:.3f}]"


def record_defect_measurement(
    case: GoldenCase,
    *,
    metric: str,
    score: float,
    threshold: float,
    threshold_passed: bool,
    scores: list[float] | None = None,
    response: AgentResponse | None = None,
    retrieved_chunks: list[Chunk] | None = None,
    wilson_interval: dict[str, float] | None = None,
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
        "scores": scores or [score],
        "retrieved_chunks": _chunk_evidence(retrieved_chunks or []),
        "response": _response_evidence(response),
        "wilson_interval": wilson_interval,
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
    if os.environ.get("PYTEST_XDIST_WORKER"):
        # `make eval-semantic` runs this tier serially specifically so this
        # hook sees every case; under `pytest -n auto` each worker/controller
        # would otherwise write its own partial results-local.json and trend
        # row, silently overwriting one another (see the deterministic
        # conftest's matching guard on its own trend append).
        return
    if _NODE_RESULTS:
        out = Path("reports/semantic/results-local.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        record = compute_trend_record(
            "semantic", _NODE_RESULTS, _SESSION_ACCUMULATOR, latency_budget_ms=LIVE_BUDGET_MS
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            settings = Settings()
        payload = {
            "run": {
                "provider": settings.provider.value,
                "model": settings.model,
                "judge_provider": (settings.judge.provider or settings.provider).value,
                "judge_model": settings.judge.model,
                "samples": settings.semantic_samples,
                "timestamp": record.timestamp,
                "git_sha": record.git_sha,
                "run_id": record.run_id,
                "workflow_run_url": os.environ.get("GITHUB_SERVER_URL", "")
                + (f"/{os.environ.get('GITHUB_REPOSITORY')}/actions/runs/{os.environ.get('GITHUB_RUN_ID')}" if os.environ.get("GITHUB_RUN_ID") else ""),
                "corpus_fingerprint": inventory()["corpus_fingerprint"],
                "dataset_inventory": inventory(),
                "evidence_class": "credentialed",
                "totals": {
                    "tokens": record.total_tokens,
                    "cost_usd": record.total_cost_usd,
                },
            },
            "trend": asdict(record),
            "outcomes": _NODE_RESULTS,
            "measurements": _SEMANTIC_MEASUREMENTS,
            "failure_details": _NODE_FAILURE_DETAILS,
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        append_trend(record)
