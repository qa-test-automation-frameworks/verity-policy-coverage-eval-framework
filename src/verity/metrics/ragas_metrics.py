"""RAGAS metric factory functions.

Each factory returns a configured RAGAS metric (Metric subclass) usable with
ragas.evaluate(dataset, metrics=[...]).

RAGAS metrics that need an LLM accept a RagasJudge adapter. Embedding-based
metrics use the local ONNX embedding model already available via ChromaDB.

Thresholds:
    Clean cases assert score >= threshold.
    expects_defect cases assert score < threshold (defect detected = test passes).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from verity.judges import ProviderJudge

# Per-metric thresholds
THRESHOLD_FAITHFULNESS: float = 0.7  # defects #1, #2, #7 fall below
THRESHOLD_CONTEXT_PRECISION: float = 0.6
THRESHOLD_ANSWER_RELEVANCY: float = 0.7


def _ragas_judge(judge: ProviderJudge) -> Any:
    from verity.judges import RagasJudge

    return RagasJudge(judge).adapter


def make_faithfulness(judge: ProviderJudge, threshold: float = THRESHOLD_FAITHFULNESS) -> Any:
    """RAGAS Faithfulness — detects hallucination, stale context, injection compliance.

    Primary targets: defect #1 (bariatric hallucination), defect #2 (stale premium),
    defect #7 (injection compliance language not grounded in authoritative corpus).
    """
    try:
        from ragas.metrics import Faithfulness
    except ImportError as exc:
        raise ImportError("ragas is required. Install with: uv sync --group semantic") from exc
    metric = Faithfulness()
    metric.llm = _ragas_judge(judge)
    return metric


def make_context_precision(
    judge: ProviderJudge, threshold: float = THRESHOLD_CONTEXT_PRECISION
) -> Any:
    """RAGAS ContextPrecision — measures retrieval precision (relevant chunks retrieved)."""
    try:
        from ragas.metrics import ContextPrecision
    except ImportError as exc:
        raise ImportError("ragas is required. Install with: uv sync --group semantic") from exc
    metric = ContextPrecision()
    metric.llm = _ragas_judge(judge)
    return metric


def make_ragas_answer_relevancy(
    judge: ProviderJudge, threshold: float = THRESHOLD_ANSWER_RELEVANCY
) -> Any:
    """RAGAS AnswerRelevancy — penalizes incomplete or off-topic answers."""
    try:
        from ragas.metrics import AnswerRelevancy
    except ImportError as exc:
        raise ImportError("ragas is required. Install with: uv sync --group semantic") from exc
    metric = AnswerRelevancy()
    metric.llm = _ragas_judge(judge)
    return metric
