"""Tier-2: G-Eval completeness — detects defect #3 (multi-hop cost calculation failure)."""

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
from verity.metrics.deepeval_metrics import THRESHOLD_COMPLETENESS, make_completeness
from verity.statistics import aggregate, threshold_pass

pytestmark = [pytest.mark.semantic, pytest.mark.live]

_ALL_CASES = load_golden(Path("datasets/golden"))
_COMPLETE_CASES = [c for c in _ALL_CASES if "g_eval_completeness" in c.semantic_metrics]
_CLEAN = [c for c in _COMPLETE_CASES if not c.expects_defect]
_DEFECT = [c for c in _COMPLETE_CASES if c.expects_defect]


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
    metric = make_completeness(judge)
    tc = LLMTestCase(
        input=case.query,
        actual_output=response.answer,
        expected_output=case.ground_truth,
    )
    metric.measure(tc)
    return float(metric.score), response, chunks


@pytest.mark.parametrize("case", _CLEAN, ids=[c.id for c in _CLEAN])
def test_clean_completeness(case: GoldenCase, settings: Settings, judge: ProviderJudge) -> None:
    samples = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    scores = [sample[0] for sample in samples]
    stat = aggregate(scores, score_threshold=THRESHOLD_COMPLETENESS)
    assert threshold_pass(stat, THRESHOLD_COMPLETENESS), (
        f"Completeness below threshold for {case.id!r}: {stat}" + wilson_interval_message(stat)
    )


@pytest.mark.parametrize("case", _DEFECT, ids=[c.id for c in _DEFECT])
def test_defect_completeness_detected(
    case: GoldenCase, settings: Settings, judge: ProviderJudge
) -> None:
    samples = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    scores = [sample[0] for sample in samples]
    stat = aggregate(scores, score_threshold=THRESHOLD_COMPLETENESS)
    passed = threshold_pass(stat, THRESHOLD_COMPLETENESS)
    record_defect_measurement(
        case,
        metric="completeness",
        score=stat.mean,
        threshold=THRESHOLD_COMPLETENESS,
        threshold_passed=passed,
        scores=scores,
        response=samples[-1][1],
        retrieved_chunks=samples[-1][2],
        wilson_interval=wilson_interval_payload(stat),
    )
