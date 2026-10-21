"""Tier-2: G-Eval PII leakage — detects defect #8 beyond scan_pii's literal regex match.

scan_pii (checks.py) catches literal name/DOB/ID strings; it misses a paraphrased or
reformatted disclosure (e.g. a birth date spelled out in words). This rubric judges intent
to disclose, not exact string match.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.semantic.conftest import (
    live_agent,
    record_defect_measurement,
    smoke_params,
    wilson_interval_message,
    wilson_interval_payload,
)
from verity.config import Settings
from verity.golden import GoldenCase, load_golden
from verity.judges import ProviderJudge
from verity.metrics.deepeval_metrics import THRESHOLD_PII_LEAKAGE, make_pii_leakage
from verity.semantic_reporting import semantic_sut_failure_message
from verity.statistics import aggregate, threshold_pass

pytestmark = [pytest.mark.semantic, pytest.mark.live]

_ALL_CASES = load_golden(Path("datasets/golden"))
_PII_CASES = [c for c in _ALL_CASES if "g_eval_pii_leakage" in c.semantic_metrics]
_CLEAN = [c for c in _PII_CASES if not c.expects_defect]
_DEFECT = [c for c in _PII_CASES if c.expects_defect]


def _score(
    case: GoldenCase, settings: Settings, judge: ProviderJudge
) -> tuple[float, object, object]:
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError:
        pytest.skip("deepeval not available")

    agent = live_agent(settings)
    response = agent.answer(case.query, member_id=case.member_id)
    failure_message = semantic_sut_failure_message(
        case.id, response.failure_category, response.answer
    )
    if failure_message is not None:
        pytest.fail(failure_message, pytrace=False)

    chunks = response.retrieved_chunks
    metric = make_pii_leakage(judge)
    tc = LLMTestCase(input=case.query, actual_output=response.answer)
    metric.measure(tc)
    return float(metric.score), response, chunks


@pytest.mark.parametrize("case", smoke_params(_CLEAN, set()))
def test_clean_pii_leakage(case: GoldenCase, settings: Settings, judge: ProviderJudge) -> None:
    """Clean cases: PII-leakage score must be >= threshold (no disclosure detected)."""
    samples = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    scores = [sample[0] for sample in samples]
    stat = aggregate(scores, score_threshold=THRESHOLD_PII_LEAKAGE)
    assert threshold_pass(stat, THRESHOLD_PII_LEAKAGE), (
        f"PII-leakage score below threshold for {case.id!r}: {stat}" + wilson_interval_message(stat)
    )


@pytest.mark.parametrize("case", smoke_params(_DEFECT, {"defect-8-pii-leakage"}))
def test_defect_pii_leakage_detected(
    case: GoldenCase, settings: Settings, judge: ProviderJudge
) -> None:
    """Defect #8: PII-leakage score must fall BELOW threshold (leak detected)."""
    samples = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    scores = [sample[0] for sample in samples]
    stat = aggregate(scores, score_threshold=THRESHOLD_PII_LEAKAGE)
    passed = threshold_pass(stat, THRESHOLD_PII_LEAKAGE)
    record_defect_measurement(
        case,
        metric="pii_leakage",
        score=stat.mean,
        threshold=THRESHOLD_PII_LEAKAGE,
        threshold_passed=passed,
        scores=scores,
        response=samples[-1][1],
        retrieved_chunks=samples[-1][2],
        wilson_interval=wilson_interval_payload(stat),
    )
