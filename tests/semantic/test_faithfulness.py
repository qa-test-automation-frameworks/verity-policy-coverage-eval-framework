"""Tier-2: RAGAS Faithfulness — detects hallucination and stale context.

Targets defects #1 (bariatric hallucination) and #2 (stale Silver premium).
Clean control cases assert faithfulness >= threshold; defect cases assert < threshold.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.semantic.conftest import live_agent
from verity.config import Settings
from verity.golden import GoldenCase, load_golden
from verity.judges import ProviderJudge
from verity.metrics.ragas_metrics import THRESHOLD_FAITHFULNESS, make_faithfulness
from verity.statistics import aggregate, threshold_pass

pytestmark = [pytest.mark.semantic, pytest.mark.live]

_ALL_CASES = load_golden(Path("datasets/golden"))
_FAITH_CASES = [c for c in _ALL_CASES if "faithfulness" in c.semantic_metrics]
_CLEAN_FAITH = [c for c in _FAITH_CASES if not c.expects_defect]
_DEFECT_FAITH = [c for c in _FAITH_CASES if c.expects_defect]

N_SAMPLES = 1  # increase to 3+ for robustness; set low for CI speed


def _score_faithfulness(
    case: GoldenCase,
    settings: Settings,
    judge: ProviderJudge,
) -> float:
    try:
        from ragas import SingleTurnSample
        from ragas.metrics import Faithfulness
    except ImportError:
        pytest.skip("ragas not available")

    agent = live_agent(settings)
    response = agent.answer(case.query, member_id=case.member_id)
    contexts = [c.text for c in agent.retriever.retrieve(case.query)]  # type: ignore[union-attr]

    metric = make_faithfulness(judge)
    sample = SingleTurnSample(
        user_input=case.query,
        response=response.answer,
        retrieved_contexts=contexts,
    )
    score: float = metric.single_turn_score(sample)
    return score


@pytest.mark.parametrize("case", _CLEAN_FAITH, ids=[c.id for c in _CLEAN_FAITH])
def test_clean_faithfulness(case: GoldenCase, settings: Settings, judge: ProviderJudge) -> None:
    """Clean cases: faithfulness must be >= threshold (no hallucination)."""
    scores = [_score_faithfulness(case, settings, judge) for _ in range(N_SAMPLES)]
    stat = aggregate(scores)
    assert threshold_pass(stat, THRESHOLD_FAITHFULNESS), (
        f"Faithfulness below threshold for {case.id!r}: {stat}"
    )


@pytest.mark.parametrize("case", _DEFECT_FAITH, ids=[c.id for c in _DEFECT_FAITH])
def test_defect_faithfulness_detected(case: GoldenCase, settings: Settings, judge: ProviderJudge) -> None:
    """Defect cases: faithfulness must fall BELOW threshold (defect detected)."""
    scores = [_score_faithfulness(case, settings, judge) for _ in range(N_SAMPLES)]
    stat = aggregate(scores)
    assert not threshold_pass(stat, THRESHOLD_FAITHFULNESS), (
        f"Defect #{case.defect_id} not detected by faithfulness check for {case.id!r}: {stat}"
    )
