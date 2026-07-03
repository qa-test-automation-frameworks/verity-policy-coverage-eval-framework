"""Tier-2: task-completion + tool-use metrics — detects defect #5."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.semantic.conftest import live_agent, record_defect_measurement
from verity.config import Settings
from verity.golden import GoldenCase, load_golden
from verity.judges import ProviderJudge
from verity.metrics.deepeval_metrics import THRESHOLD_COMPLETENESS, make_completeness
from verity.statistics import aggregate, threshold_pass

pytestmark = [pytest.mark.semantic, pytest.mark.live]

_ALL_CASES = load_golden(Path("datasets/golden"))
_TOOL_CASES = [c for c in _ALL_CASES if "task_completion" in c.semantic_metrics]
_CLEAN = [c for c in _TOOL_CASES if not c.expects_defect]
_DEFECT = [c for c in _TOOL_CASES if c.expects_defect]


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
def test_clean_task_completion(case: GoldenCase, settings: Settings, judge: ProviderJudge) -> None:
    samples = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    scores = [sample[0] for sample in samples]
    stat = aggregate(scores, score_threshold=THRESHOLD_COMPLETENESS)
    assert threshold_pass(stat, THRESHOLD_COMPLETENESS), (
        f"Task completion below threshold for {case.id!r}: {stat}"
    )


@pytest.mark.parametrize("case", _DEFECT, ids=[c.id for c in _DEFECT])
def test_defect_tool_use_detected(
    case: GoldenCase, settings: Settings, judge: ProviderJudge
) -> None:
    """Defect #5: tool skipped or args wrong — task completion must fall below threshold."""
    samples = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    scores = [sample[0] for sample in samples]
    stat = aggregate(scores, score_threshold=THRESHOLD_COMPLETENESS)
    passed = threshold_pass(stat, THRESHOLD_COMPLETENESS)
    record_defect_measurement(
        case,
        metric="task_completion",
        score=stat.mean,
        threshold=THRESHOLD_COMPLETENESS,
        threshold_passed=passed,
        scores=scores,
        response=samples[-1][1],
        retrieved_chunks=samples[-1][2],
    )
