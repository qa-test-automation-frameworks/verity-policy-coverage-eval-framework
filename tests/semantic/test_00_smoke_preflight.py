"""Low-cost judge preflight so malformed scoring output fails before SUT calls."""

from __future__ import annotations

import pytest

from verity.judges import ProviderJudge
from verity.metrics.deepeval_metrics import THRESHOLD_COMPLETENESS, make_completeness

pytestmark = [pytest.mark.semantic, pytest.mark.live]


@pytest.mark.smoke
def test_judge_json_preflight(judge: ProviderJudge) -> None:
    """Verify the configured judge can score a fixed completeness canary."""
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
