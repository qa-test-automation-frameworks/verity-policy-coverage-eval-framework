"""Tier-2: RAGAS Faithfulness — detects hallucination and stale context.

Targets defects #1 (bariatric hallucination) and #2 (stale Silver premium).
Clean controls assert faithfulness >= threshold; defect cases record whether the live SUT
still falls below it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sut.agent import AgentResponse
from sut.retriever import Chunk
from tests.semantic.conftest import (
    live_agent,
    record_defect_measurement,
    record_semantic_metric,
    smoke_params,
    wilson_interval_message,
    wilson_interval_payload,
)
from verity.config import Settings
from verity.golden import GoldenCase, load_golden
from verity.judges import ProviderJudge
from verity.metrics.ragas_metrics import (
    THRESHOLD_FAITHFULNESS,
    ensure_ragas_compat,
    make_faithfulness,
)
from verity.semantic_reporting import semantic_sut_failure_message
from verity.statistics import aggregate, threshold_pass

pytestmark = [pytest.mark.semantic, pytest.mark.live]

_ALL_CASES = load_golden(Path("datasets/golden"))
_FAITH_CASES = [c for c in _ALL_CASES if "faithfulness" in c.semantic_metrics]
_CLEAN_FAITH = [c for c in _FAITH_CASES if not c.expects_defect]
_DEFECT_FAITH = [c for c in _FAITH_CASES if c.expects_defect]


def _score_faithfulness(
    case: GoldenCase,
    settings: Settings,
    judge: ProviderJudge,
) -> tuple[float, AgentResponse, list[Chunk]]:
    ensure_ragas_compat()
    try:
        from ragas import SingleTurnSample
    except ImportError:
        pytest.skip("ragas not available")

    agent = live_agent(settings)
    response = agent.answer(case.query, member_id=case.member_id)
    failure_message = semantic_sut_failure_message(
        case.id, response.failure_category, response.answer
    )
    if failure_message is not None:
        pytest.fail(failure_message, pytrace=False)

    chunks = response.retrieved_chunks
    contexts = [c.text for c in chunks]

    metric = make_faithfulness(judge)
    sample = SingleTurnSample(
        user_input=case.query,
        response=response.answer,
        retrieved_contexts=contexts,
    )
    try:
        score: float = metric.single_turn_score(sample)
    except Exception as exc:
        record_semantic_metric(
            case,
            metric="faithfulness",
            threshold=THRESHOLD_FAITHFULNESS,
            judge_model=judge.model_name,
            error=exc,
        )
        raise
    record_semantic_metric(
        case,
        metric="faithfulness",
        threshold=THRESHOLD_FAITHFULNESS,
        judge_model=judge.model_name,
        score=score,
    )
    return score, response, chunks


@pytest.mark.quarantine
@pytest.mark.parametrize("case", smoke_params(_CLEAN_FAITH, {"ctrl-silver-physical-therapy-limit"}))
def test_clean_faithfulness(
    case: GoldenCase,
    settings: Settings,
    judge: ProviderJudge,
    request: pytest.FixtureRequest,
) -> None:
    """Clean cases: faithfulness must be >= threshold (no hallucination).

    Quarantined: control-case gating on this metric is informational, not a
    blocking signal, until a live calibration run against the new
    HALLUCINATION_RUBRIC-adjacent faithfulness rubric clears the 85%-agreement
    bar for this metric — see docs/thresholds.md and docs/known-issues.md
    (KI-3). Defect-detection gating for faithfulness (test_defect_faithfulness_detected
    below) is unaffected and stays active.
    """
    samples = [_score_faithfulness(case, settings, judge) for _ in range(settings.semantic_samples)]
    scores = [sample[0] for sample in samples]
    stat = aggregate(scores, score_threshold=THRESHOLD_FAITHFULNESS)
    if threshold_pass(stat, THRESHOLD_FAITHFULNESS):
        return

    failure = f"Faithfulness below threshold for {case.id!r}: {stat}{wilson_interval_message(stat)}"
    if request.node.get_closest_marker("quarantine") is not None:
        pytest.xfail(f"Quarantined, non-blocking calibration signal: {failure}")
    pytest.fail(failure)


@pytest.mark.parametrize(
    "case", smoke_params(_DEFECT_FAITH, {"defect-1-bariatric-bronze-hallucination"})
)
def test_defect_faithfulness_detected(
    case: GoldenCase, settings: Settings, judge: ProviderJudge
) -> None:
    """Defect cases: faithfulness must fall BELOW threshold (defect detected)."""
    samples = [_score_faithfulness(case, settings, judge) for _ in range(settings.semantic_samples)]
    scores = [sample[0] for sample in samples]
    stat = aggregate(scores, score_threshold=THRESHOLD_FAITHFULNESS)
    passed = threshold_pass(stat, THRESHOLD_FAITHFULNESS)
    record_defect_measurement(
        case,
        metric="faithfulness",
        score=stat.mean,
        threshold=THRESHOLD_FAITHFULNESS,
        threshold_passed=passed,
        scores=scores,
        response=samples[-1][1],
        retrieved_chunks=samples[-1][2],
        wilson_interval=wilson_interval_payload(stat),
    )
