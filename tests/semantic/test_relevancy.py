"""Tier-2: Answer relevancy across clean control cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.semantic.conftest import live_agent, wilson_interval_message
from verity.config import Settings
from verity.golden import GoldenCase, load_golden
from verity.judges import ProviderJudge
from verity.metrics.deepeval_metrics import THRESHOLD_ANSWER_RELEVANCY, make_answer_relevancy
from verity.statistics import aggregate, threshold_pass

pytestmark = [pytest.mark.semantic, pytest.mark.live]

_ALL_CASES = load_golden(Path("datasets/golden"))
_RELEVANCY_CASES = [
    c for c in _ALL_CASES if "answer_relevancy" in c.semantic_metrics and not c.expects_defect
]


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
    metric = make_answer_relevancy(judge)
    tc = LLMTestCase(
        input=case.query,
        actual_output=response.answer,
    )
    metric.measure(tc)
    return float(metric.score), response, chunks


@pytest.mark.quarantine
@pytest.mark.parametrize("case", _RELEVANCY_CASES, ids=[c.id for c in _RELEVANCY_CASES])
def test_answer_relevancy(case: GoldenCase, settings: Settings, judge: ProviderJudge) -> None:
    """Clean cases must return a relevant, on-topic answer.

    Quarantined: the committed live control run recorded multiple failures on
    this exact assertion (see the Control-Case Results section of
    docs/defects-caught.md); gating on it is informational until a live
    calibration run against `datasets/calibration/labeled.yaml`'s
    `answer_relevancy` cases clears the 85%-agreement bar — see
    docs/thresholds.md and docs/known-issues.md (KI-3).
    """
    samples = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    scores = [sample[0] for sample in samples]
    stat = aggregate(scores, score_threshold=THRESHOLD_ANSWER_RELEVANCY)
    assert threshold_pass(stat, THRESHOLD_ANSWER_RELEVANCY), (
        f"Answer relevancy below threshold for {case.id!r}: {stat}" + wilson_interval_message(stat)
    )
