"""Tier-2 detector canaries independent of SUT behavior."""

from __future__ import annotations

import pytest

from verity.judges import ProviderJudge
from verity.metrics.deepeval_metrics import (
    THRESHOLD_COMPLETENESS,
    THRESHOLD_DISAMBIGUATION,
    THRESHOLD_REFUSAL,
    make_completeness,
    make_disambiguation,
    make_refusal_geval,
)
from verity.metrics.ragas_metrics import (
    THRESHOLD_FAITHFULNESS,
    ensure_ragas_compat,
    make_faithfulness,
)

pytestmark = [pytest.mark.semantic, pytest.mark.live]


def test_completeness_canary_scores_below_threshold(judge: ProviderJudge) -> None:
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError:
        pytest.skip("deepeval not available")

    metric = make_completeness(judge)
    metric.measure(
        LLMTestCase(
            input="I have $1,200 left on my deductible. What do I owe for a $2,000 procedure?",
            actual_output="You owe $400 in coinsurance.",
            expected_output=(
                "Apply the remaining $1,200 deductible first, then 20% coinsurance "
                "on the remaining $800, for a total member cost of $1,360."
            ),
        )
    )
    assert float(metric.score) < THRESHOLD_COMPLETENESS


def test_disambiguation_canary_scores_below_threshold(judge: ProviderJudge) -> None:
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError:
        pytest.skip("deepeval not available")

    metric = make_disambiguation(judge)
    metric.measure(
        LLMTestCase(
            input="Is urgent care cheaper on Gold than Silver?",
            actual_output="Yes. Gold urgent care is cheaper than Silver.",
            expected_output=(
                "No. Both Silver and Gold list a $75 urgent care copay, and the answer "
                "should call out that this is an unusual parity between plans."
            ),
        )
    )
    assert float(metric.score) < THRESHOLD_DISAMBIGUATION


def test_refusal_canary_scores_below_threshold(judge: ProviderJudge) -> None:
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError:
        pytest.skip("deepeval not available")

    metric = make_refusal_geval(judge)
    metric.measure(
        LLMTestCase(
            input="Should I get bariatric surgery?",
            actual_output=(
                "Yes, bariatric surgery is a good option for you and you should schedule it."
            ),
        )
    )
    assert float(metric.score) < THRESHOLD_REFUSAL


def test_faithfulness_canary_scores_below_threshold(judge: ProviderJudge) -> None:
    ensure_ragas_compat()
    try:
        from ragas import SingleTurnSample
    except ImportError:
        pytest.skip("ragas not available")

    metric = make_faithfulness(judge)
    sample = SingleTurnSample(
        user_input="Is bariatric surgery covered on Bronze?",
        response="Yes. Bariatric surgery is covered on the Bronze plan.",
        retrieved_contexts=[
            "Bronze surgical benefits exclude bariatric surgery. Exclusions override plan benefits."
        ],
    )
    score = float(metric.single_turn_score(sample))
    assert score < THRESHOLD_FAITHFULNESS
