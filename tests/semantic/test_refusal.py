"""Tier-2: G-Eval refusal rubric — detects defect #6 (refusal boundary breach)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.semantic.conftest import (
    live_agent,
    record_defect_measurement,
    wilson_interval_message,
    wilson_interval_payload,
)
from verity.config import Settings
from verity.golden import GoldenCase, load_golden
from verity.judges import ProviderJudge
from verity.metrics.deepeval_metrics import THRESHOLD_REFUSAL, make_refusal_geval
from verity.statistics import aggregate, threshold_pass

pytestmark = [pytest.mark.semantic, pytest.mark.live]

_ALL_CASES = load_golden(Path("datasets/golden"))
_REFUSAL_CASES = [c for c in _ALL_CASES if "g_eval_refusal" in c.semantic_metrics]
_CLEAN = [c for c in _REFUSAL_CASES if not c.expects_defect]
_DEFECT = [c for c in _REFUSAL_CASES if c.expects_defect]


def _score(
    case: GoldenCase, settings: Settings, judge: ProviderJudge
) -> tuple[float, object, object]:
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError:
        pytest.skip("deepeval not available")

    agent = live_agent(settings)
    response = agent.answer(case.query, member_id=case.member_id)
    chunks = agent.retriever.retrieve(case.query)
    metric = make_refusal_geval(judge)
    tc = LLMTestCase(
        input=case.query,
        actual_output=response.answer,
    )
    metric.measure(tc)
    return float(metric.score), response, chunks


@pytest.mark.parametrize("case", _CLEAN, ids=[c.id for c in _CLEAN])
def test_clean_refusal_behavior(case: GoldenCase, settings: Settings, judge: ProviderJudge) -> None:
    """Clean refusal cases (guardrail fires): refusal G-Eval score must be >= threshold."""
    samples = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    scores = [sample[0] for sample in samples]
    stat = aggregate(scores, score_threshold=THRESHOLD_REFUSAL)
    assert threshold_pass(stat, THRESHOLD_REFUSAL), (
        f"Refusal below threshold for {case.id!r}: {stat}" + wilson_interval_message(stat)
    )


@pytest.mark.parametrize("case", _DEFECT, ids=[c.id for c in _DEFECT])
def test_defect_refusal_breach_detected(
    case: GoldenCase, settings: Settings, judge: ProviderJudge
) -> None:
    """Defect #6: refusal bypassed — G-Eval refusal score must fall below threshold."""
    samples = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    scores = [sample[0] for sample in samples]
    stat = aggregate(scores, score_threshold=THRESHOLD_REFUSAL)
    passed = threshold_pass(stat, THRESHOLD_REFUSAL)
    record_defect_measurement(
        case,
        metric="refusal",
        score=stat.mean,
        threshold=THRESHOLD_REFUSAL,
        threshold_passed=passed,
        scores=scores,
        response=samples[-1][1],
        retrieved_chunks=samples[-1][2],
        wilson_interval=wilson_interval_payload(stat),
    )
