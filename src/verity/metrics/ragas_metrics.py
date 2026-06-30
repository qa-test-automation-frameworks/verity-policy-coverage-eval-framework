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

import importlib
import sys
import types
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from verity.judges import ProviderJudge


def ensure_ragas_compat() -> None:
    """Install a narrow compatibility shim for RAGAS optional imports."""
    module_name = "langchain_community.chat_models.vertexai"
    if module_name in sys.modules:
        return
    try:
        importlib.import_module(module_name)
        return
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            raise

    module = types.ModuleType(module_name)

    class ChatVertexAI:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise ImportError(
                "ChatVertexAI moved out of langchain-community; install the provider "
                "integration before using Vertex-backed RAGAS judges."
            )

    module.ChatVertexAI = ChatVertexAI
    sys.modules[module_name] = module
    parent = importlib.import_module("langchain_community.chat_models")
    parent.vertexai = module


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
    ensure_ragas_compat()
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
    ensure_ragas_compat()
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
    ensure_ragas_compat()
    try:
        from ragas.metrics import AnswerRelevancy
    except ImportError as exc:
        raise ImportError("ragas is required. Install with: uv sync --group semantic") from exc
    metric = AnswerRelevancy()
    metric.llm = _ragas_judge(judge)
    return metric
