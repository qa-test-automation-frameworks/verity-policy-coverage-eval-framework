"""Tier-2: G-Eval completeness — detects defect #3 (multi-hop cost calculation failure)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.semantic.conftest import live_agent
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


def _score(case: GoldenCase, settings: Settings, judge: ProviderJudge) -> float:
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError:
        pytest.skip("deepeval not available")

    agent = live_agent(settings)
    response = agent.answer(case.query, member_id=case.member_id)
    metric = make_completeness(judge)
    tc = LLMTestCase(
        input=case.query,
        actual_output=response.answer,
        expected_output=case.ground_truth,
    )
    metric.measure(tc)
    return float(metric.score)


@pytest.mark.parametrize("case", _CLEAN, ids=[c.id for c in _CLEAN])
def test_clean_completeness(case: GoldenCase, settings: Settings, judge: ProviderJudge) -> None:
    scores = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    stat = aggregate(scores)
    assert threshold_pass(stat, THRESHOLD_COMPLETENESS), (
        f"Completeness below threshold for {case.id!r}: {stat}"
    )


@pytest.mark.parametrize("case", _DEFECT, ids=[c.id for c in _DEFECT])
def test_defect_completeness_detected(
    case: GoldenCase, settings: Settings, judge: ProviderJudge
) -> None:
    scores = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    stat = aggregate(scores)
    assert not threshold_pass(stat, THRESHOLD_COMPLETENESS), (
        f"Defect #{case.defect_id} not detected by completeness for {case.id!r}: {stat}"
    )
