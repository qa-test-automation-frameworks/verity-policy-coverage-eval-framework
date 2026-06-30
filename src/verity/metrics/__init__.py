"""Semantic evaluation metrics for Tier-2.

Provides DeepEval and RAGAS metrics configured with G-Eval rubrics and
statistical thresholds. All metrics accept a ProviderJudge for flexible
provider routing (same config as the SUT).

Import structure (all optional — requires 'semantic' extra):
    from verity.metrics.deepeval_metrics import (
        make_hallucination, make_answer_relevancy, make_completeness,
        make_disambiguation, make_refusal_geval, make_tool_correctness,
    )
    from verity.metrics.ragas_metrics import (
        make_faithfulness, make_context_precision, make_ragas_answer_relevancy,
    )
"""

from __future__ import annotations
