"""Tier-2: G-Eval refusal rubric — detects defect #6 (refusal boundary breach)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.semantic.conftest import live_agent
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


def _score(case: GoldenCase, settings: Settings, judge: ProviderJudge) -> float:
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError:
        pytest.skip("deepeval not available")

    agent = live_agent(settings)
    response = agent.answer(case.query, member_id=case.member_id)
    metric = make_refusal_geval(judge)
    tc = LLMTestCase(
        input=case.query,
        actual_output=response.answer,
    )
    metric.measure(tc)
    return float(metric.score)


@pytest.mark.parametrize("case", _CLEAN, ids=[c.id for c in _CLEAN])
def test_clean_refusal_behavior(case: GoldenCase, settings: Settings, judge: ProviderJudge) -> None:
    """Clean refusal cases (guardrail fires): refusal G-Eval score must be >= threshold."""
    scores = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    stat = aggregate(scores)
    assert threshold_pass(stat, THRESHOLD_REFUSAL), (
        f"Refusal below threshold for {case.id!r}: {stat}"
    )


@pytest.mark.parametrize("case", _DEFECT, ids=[c.id for c in _DEFECT])
def test_defect_refusal_breach_detected(
    case: GoldenCase, settings: Settings, judge: ProviderJudge
) -> None:
    """Defect #6: refusal bypassed — G-Eval refusal score must fall below threshold."""
    scores = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    stat = aggregate(scores)
    assert not threshold_pass(stat, THRESHOLD_REFUSAL), (
        f"Defect #{case.defect_id} not detected by refusal G-Eval for {case.id!r}: {stat}"
    )
