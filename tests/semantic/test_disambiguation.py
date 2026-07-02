"""Tier-2: G-Eval disambiguation — detects defect #4 (contradiction not surfaced)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.semantic.conftest import live_agent, record_defect_measurement
from verity.config import Settings
from verity.golden import GoldenCase, load_golden
from verity.judges import ProviderJudge
from verity.metrics.deepeval_metrics import THRESHOLD_DISAMBIGUATION, make_disambiguation
from verity.statistics import aggregate, threshold_pass

pytestmark = [pytest.mark.semantic, pytest.mark.live]

_ALL_CASES = load_golden(Path("datasets/golden"))
_DISAMBIG_CASES = [c for c in _ALL_CASES if "g_eval_disambiguation" in c.semantic_metrics]
_CLEAN = [c for c in _DISAMBIG_CASES if not c.expects_defect]
_DEFECT = [c for c in _DISAMBIG_CASES if c.expects_defect]


def _score(case: GoldenCase, settings: Settings, judge: ProviderJudge) -> float:
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError:
        pytest.skip("deepeval not available")

    agent = live_agent(settings)
    response = agent.answer(case.query, member_id=case.member_id)
    metric = make_disambiguation(judge)
    tc = LLMTestCase(
        input=case.query,
        actual_output=response.answer,
        expected_output=case.ground_truth,
    )
    metric.measure(tc)
    return float(metric.score)


@pytest.mark.parametrize("case", _CLEAN, ids=[c.id for c in _CLEAN])
def test_clean_disambiguation(case: GoldenCase, settings: Settings, judge: ProviderJudge) -> None:
    scores = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    stat = aggregate(scores, score_threshold=THRESHOLD_DISAMBIGUATION)
    assert threshold_pass(stat, THRESHOLD_DISAMBIGUATION), (
        f"Disambiguation below threshold for {case.id!r}: {stat}"
    )


@pytest.mark.parametrize("case", _DEFECT, ids=[c.id for c in _DEFECT])
def test_defect_disambiguation_detected(
    case: GoldenCase, settings: Settings, judge: ProviderJudge
) -> None:
    scores = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    stat = aggregate(scores, score_threshold=THRESHOLD_DISAMBIGUATION)
    passed = threshold_pass(stat, THRESHOLD_DISAMBIGUATION)
    record_defect_measurement(
        case,
        metric="disambiguation",
        score=stat.mean,
        threshold=THRESHOLD_DISAMBIGUATION,
        threshold_passed=passed,
    )
