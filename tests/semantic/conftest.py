"""Shared fixtures for the semantic (Tier-2) evaluation suite.

ALL tests here are marked `semantic` and `live` -- they make real LLM calls
via the configured provider and are NOT run in the PR gate (see pr-gate.yml).

Run with: make eval-semantic  (requires API key in .env)
"""

from __future__ import annotations

import json
import logging
import os
import warnings
from collections.abc import Generator
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sut.agent import AgentResponse, CoverageAgent
from sut.retriever import Chunk, PolicyRetriever
from verity.config import Settings
from verity.cost import RunAccumulator, reset_current_test_id, set_current_test_id
from verity.golden import GoldenCase, load_golden
from verity.judges import ProviderJudge
from verity.latency import LIVE_BUDGET_MS
from verity.providers import RATE_LIMIT_STOP_THRESHOLD, LLMProvider
from verity.reporting import (
    build_usage_report,
    render_cost_summary,
    render_request_ledger,
    render_usage_summary,
    write_step_summary,
)
from verity.semantic_reporting import (
    append_case_evidence_event,
    append_failure_event,
    failure_reason,
)
from verity.statistics import StatResult, pass_rate_wilson_interval
from verity.trends import append_trend, compute_trend_record

pytestmark = [pytest.mark.semantic, pytest.mark.live]

_GOLDEN_DIR = Path("datasets/golden")
logger = logging.getLogger(__name__)


def smoke_params(cases, selected_ids: set[str]):
    """Mark selected parametrized cases for the low-volume live smoke suite."""
    return [
        pytest.param(
            case,
            id=case.id,
            marks=pytest.mark.smoke if case.id in selected_ids else (),
        )
        for case in cases
    ]


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
        # Rate-limit failures must reach the shared circuit breaker without
        # hidden SDK retries, even when a developer's .env sets VERITY_RETRIES.
        return Settings(sut_profile="seeded", retries=0)


@pytest.fixture(scope="session")
def judge(settings: Settings) -> ProviderJudge:
    return ProviderJudge(settings=settings, accumulator=_SESSION_ACCUMULATOR)


@pytest.fixture(scope="session")
def golden_cases() -> list[GoldenCase]:
    return load_golden(_GOLDEN_DIR)


_SESSION_ACCUMULATOR = RunAccumulator()
_RATE_LIMIT_STOP_REPORTED = False


def live_agent(settings: Settings) -> CoverageAgent:
    """Create a live CoverageAgent using the real local ONNX retriever."""
    provider = LLMProvider(settings, _SESSION_ACCUMULATOR)
    retriever = PolicyRetriever(settings.retrieval)
    return CoverageAgent(settings=settings, retriever=retriever, provider=provider)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(
    item: pytest.Item, nextitem: pytest.Item | None
) -> Generator[None, None, None]:
    """Attribute provider calls made during fixtures, test code, and teardown."""
    token = set_current_test_id(item.nodeid)
    try:
        yield
    finally:
        reset_current_test_id(token)


_NODE_RESULTS: dict[str, str] = {}
_SEMANTIC_MEASUREMENTS: dict[str, dict[str, object]] = {}
_NODE_FAILURE_DETAILS: dict[str, str] = {}


def _case_evidence_path() -> Path:
    return Path(
        os.environ.get(
            "VERITY_SEMANTIC_CASE_EVIDENCE_PATH",
            "reports/semantic/case-evidence.jsonl",
        )
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    """Start each run with a fresh case-evidence artifact and disclose its mode."""
    if os.environ.get("PYTEST_XDIST_WORKER"):
        return
    path = _case_evidence_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    verbosity = os.environ.get("VERITY_SEMANTIC_VERBOSITY", "standard")
    if verbosity != "verbose":
        append_case_evidence_event(
            path,
            event={
                "schema_version": 1,
                "record_type": "case_evidence_mode",
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "verbosity": verbosity,
                "model_answers_recorded": False,
                "reason": "Set VERITY_SEMANTIC_VERBOSITY=verbose to retain case traces.",
            },
        )


@pytest.fixture(autouse=True)
def capture_semantic_case_answers(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Record final SUT answers and supporting evidence only in verbose runs."""
    if os.environ.get("VERITY_SEMANTIC_VERBOSITY", "standard") != "verbose":
        return

    original_answer = CoverageAgent.answer
    sample_number = 0
    case = getattr(request.node, "callspec", None)
    case = case.params.get("case") if case is not None else None
    case_id = getattr(case, "id", request.node.name)

    def _answer_with_evidence(
        agent: CoverageAgent, query: str, *args: Any, **kwargs: Any
    ) -> AgentResponse:
        nonlocal sample_number
        response = original_answer(agent, query, *args, **kwargs)
        sample_number += 1
        event = {
            "schema_version": 1,
            "record_type": "sut_response",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "nodeid": request.node.nodeid,
            "case_id": case_id,
            "sample": sample_number,
            "query": query,
            "expected_behavior": getattr(case, "behavior", None),
            "expected_output": getattr(case, "ground_truth", None),
            "answer": response.answer,
            "citations": response.citations,
            "tool_invocations": [
                call.model_dump(mode="json") for call in response.tool_invocations
            ],
            "retrieved_chunks": [
                {
                    "source": chunk.source,
                    "section": chunk.section,
                    "chunk_id": chunk.chunk_id,
                    "rank": chunk.rank,
                    "score": chunk.score,
                    "corpus_fingerprint": chunk.corpus_fingerprint,
                    "text": chunk.text,
                }
                for chunk in response.retrieved_chunks
            ],
            "refused": response.refused,
            "refusal_reason": response.refusal_reason,
            "failure_category": response.failure_category,
            "requires_human_review": response.requires_human_review,
            "usage": {
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
                "total_tokens": response.total_tokens,
                "estimated_cost_usd": response.estimated_cost_usd,
            },
            "trace_id": response.trace_id,
        }
        try:
            append_case_evidence_event(_case_evidence_path(), event=event)
        except OSError:
            logger.exception("Could not persist verbose semantic case evidence")
        return response

    monkeypatch.setattr(CoverageAgent, "answer", _answer_with_evidence)


def record_semantic_metric(
    case: GoldenCase,
    *,
    metric: str,
    threshold: float,
    judge_model: str | None = None,
    score: float | None = None,
    reason: str | None = None,
    error: Exception | None = None,
) -> None:
    """Append judge score/rationale or parse failure to the verbose case trace."""
    if os.environ.get("VERITY_SEMANTIC_VERBOSITY", "standard") != "verbose":
        return
    event: dict[str, object] = {
        "schema_version": 1,
        "record_type": "judge_result",
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "case_id": case.id,
        "metric": metric,
        "judge_model": judge_model,
        "threshold": threshold,
        "status": "error" if error is not None else "scored",
    }
    if score is not None:
        event["score"] = score
    if reason:
        event["reason"] = reason
    if error is not None:
        event["error_type"] = type(error).__name__
        event["error"] = str(error)[:5000]
    try:
        append_case_evidence_event(_case_evidence_path(), event=event)
    except OSError:
        logger.exception("Could not persist verbose semantic judge evidence")


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
    global _RATE_LIMIT_STOP_REPORTED
    outcome = yield
    if call.when == "call":
        report = outcome.get_result()
        _NODE_RESULTS[item.nodeid] = report.outcome
        if report.failed:
            longrepr = str(report.longrepr)
            try:
                event_path = Path(
                    os.environ.get(
                        "VERITY_SEMANTIC_FAILURES_PATH",
                        "reports/semantic/failures.jsonl",
                    )
                )
                event = append_failure_event(event_path, nodeid=item.nodeid, longrepr=longrepr)
                _NODE_FAILURE_DETAILS[item.nodeid] = str(event["details"])
                terminal = item.config.pluginmanager.get_plugin("terminalreporter")
                if terminal is not None:
                    terminal.write_line(f"SEMANTIC_FAILURE {item.nodeid}: {event['reason']}")
            except OSError as exc:
                # Preserve the original test failure, but make a broken journal
                # visible instead of silently losing the diagnostic.
                _NODE_FAILURE_DETAILS[item.nodeid] = failure_reason(longrepr)
                terminal = item.config.pluginmanager.get_plugin("terminalreporter")
                if terminal is not None:
                    terminal.write_line(f"SEMANTIC_FAILURE_JOURNAL_ERROR {item.nodeid}: {exc}")

    if (
        not os.environ.get("PYTEST_XDIST_WORKER")
        and _SESSION_ACCUMULATOR.rate_limit_responses >= RATE_LIMIT_STOP_THRESHOLD
    ):
        message = (
            "SEMANTIC_RATE_LIMIT_STOP: stopping after "
            f"{RATE_LIMIT_STOP_THRESHOLD} provider HTTP 429 "
            "responses; no further semantic tests will run."
        )
        if not getattr(item.session, "shouldfail", None):
            item.session.shouldfail = message
        if not _RATE_LIMIT_STOP_REPORTED:
            terminal = item.config.pluginmanager.get_plugin("terminalreporter")
            if terminal is not None:
                terminal.write_line(message)
            _RATE_LIMIT_STOP_REPORTED = True


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    usage_report = build_usage_report(_SESSION_ACCUMULATOR, _NODE_RESULTS)
    usage_summary = render_usage_summary(usage_report)
    summary = render_cost_summary(_SESSION_ACCUMULATOR) + usage_summary
    write_step_summary(summary)
    terminal = session.config.pluginmanager.get_plugin("terminalreporter")
    if terminal is not None and not os.environ.get("PYTEST_XDIST_WORKER"):
        verbosity = os.environ.get("VERITY_SEMANTIC_VERBOSITY", "standard")
        terminal.write_sep("=", "LLM API request and token usage")
        rendered_usage = render_usage_summary(usage_report, include_tests=verbosity != "quiet")
        for line in rendered_usage.splitlines():
            terminal.write_line(line)
        if verbosity == "verbose":
            for line in render_request_ledger(usage_report).splitlines():
                terminal.write_line(line)
    if os.environ.get("PYTEST_XDIST_WORKER"):
        # `make eval-semantic` runs this tier serially specifically so this
        # hook sees every case; under `pytest -n auto` each worker/controller
        # would otherwise write its own partial results-local.json and trend
        # row, silently overwriting one another (see the deterministic
        # conftest's matching guard on its own trend append).
        return
    usage_path = Path("reports/semantic/usage.json")
    usage_path.parent.mkdir(parents=True, exist_ok=True)
    usage_path.write_text(json.dumps(usage_report, indent=2), encoding="utf-8")
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
                "totals": {
                    "tokens": record.total_tokens,
                    "cost_usd": record.total_cost_usd,
                    "requests": usage_report["suite"]["requests"],
                    "successful_requests": usage_report["suite"]["succeeded"],
                    "failed_requests": usage_report["suite"]["failed"],
                    "incomplete_requests": usage_report["suite"]["incomplete"],
                },
                "usage_report": "usage.json",
            },
            "trend": asdict(record),
            "outcomes": _NODE_RESULTS,
            "measurements": _SEMANTIC_MEASUREMENTS,
            "failure_details": _NODE_FAILURE_DETAILS,
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        append_trend(record)
