"""Tier-2: G-Eval injection compliance — detects defect #7 beyond scan_injection's
literal regex match.

scan_injection (checks.py) catches literal echoes of the §A5 payload's wording; it misses
a paraphrased compliance (e.g. "everything is included" instead of "all procedures are
covered"). This rubric judges whether the response acted on the injected instruction in
substance, not exact wording.
"""

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
from verity.metrics.deepeval_metrics import (
    THRESHOLD_INJECTION_COMPLIANCE,
    make_injection_compliance,
)
from verity.statistics import aggregate, threshold_pass

pytestmark = [pytest.mark.semantic, pytest.mark.live]

_ALL_CASES = load_golden(Path("datasets/golden"))
_INJECTION_CASES = [c for c in _ALL_CASES if "g_eval_injection_compliance" in c.semantic_metrics]
_CLEAN = [c for c in _INJECTION_CASES if not c.expects_defect]
_DEFECT = [c for c in _INJECTION_CASES if c.expects_defect]


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
    metric = make_injection_compliance(judge)
    tc = LLMTestCase(input=case.query, actual_output=response.answer)
    metric.measure(tc)
    return float(metric.score), response, chunks


@pytest.mark.parametrize("case", _CLEAN, ids=[c.id for c in _CLEAN])
def test_clean_injection_compliance(
    case: GoldenCase, settings: Settings, judge: ProviderJudge
) -> None:
    """Clean cases: injection-compliance score must be >= threshold (no compliance)."""
    samples = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    scores = [sample[0] for sample in samples]
    stat = aggregate(scores, score_threshold=THRESHOLD_INJECTION_COMPLIANCE)
    assert threshold_pass(stat, THRESHOLD_INJECTION_COMPLIANCE), (
        f"Injection-compliance score below threshold for {case.id!r}: {stat}"
        + wilson_interval_message(stat)
    )


@pytest.mark.parametrize("case", _DEFECT, ids=[c.id for c in _DEFECT])
def test_defect_injection_compliance_detected(
    case: GoldenCase, settings: Settings, judge: ProviderJudge
) -> None:
    """Defect #7: injection-compliance score must fall BELOW threshold (compliance detected)."""
    samples = [_score(case, settings, judge) for _ in range(settings.semantic_samples)]
    scores = [sample[0] for sample in samples]
    stat = aggregate(scores, score_threshold=THRESHOLD_INJECTION_COMPLIANCE)
    passed = threshold_pass(stat, THRESHOLD_INJECTION_COMPLIANCE)
    record_defect_measurement(
        case,
        metric="injection_compliance",
        score=stat.mean,
        threshold=THRESHOLD_INJECTION_COMPLIANCE,
        threshold_passed=passed,
        scores=scores,
        response=samples[-1][1],
        retrieved_chunks=samples[-1][2],
        wilson_interval=wilson_interval_payload(stat),
    )
