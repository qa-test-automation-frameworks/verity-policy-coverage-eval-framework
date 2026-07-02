"""RAGAS metric factory functions.

Each factory returns a configured RAGAS metric (Metric subclass) usable with
ragas.evaluate(dataset, metrics=[...]).

RAGAS metrics that need an LLM accept a RagasJudge adapter. Embedding-based
metrics use the local ONNX embedding model already available via ChromaDB.

Thresholds:
    Clean cases assert score >= threshold.
    expects_defect cases record whether score < threshold (defect detected) or >= threshold (fixed).
"""

from __future__ import annotations

import importlib
import sys
import types
import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from verity.judges import ProviderJudge


def ensure_ragas_compat() -> None:
    """Install a narrow compatibility shim for RAGAS optional imports."""
    module_name = "langchain_community.chat_models.vertexai"
    if module_name in sys.modules:
        return
    try:
        # langchain-community emits a package-wide sunset DeprecationWarning on
        # import (see https://github.com/langchain-ai/langchain-community/issues/674).
        # ragas still depends on it transitively for this compat shim; there is
        # no non-deprecated import path today, so this is a deliberate, narrowly
        # scoped suppression rather than an unaddressed warning.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
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

    module.ChatVertexAI = ChatVertexAI  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        parent = importlib.import_module("langchain_community.chat_models")
    parent.vertexai = module  # type: ignore[attr-defined]


# Per-metric thresholds
THRESHOLD_FAITHFULNESS: float = 0.7  # defects #1, #2, #7 fall below
THRESHOLD_CONTEXT_PRECISION: float = 0.6
THRESHOLD_CONTEXT_RECALL: float = 0.6
THRESHOLD_ANSWER_RELEVANCY: float = 0.7


def _ragas_judge(judge: ProviderJudge) -> Any:
    from verity.judges import RagasJudge

    return RagasJudge(judge).adapter


def _import_ragas_metric_class(name: str) -> Any:
    """Import a metric class from ragas.metrics, suppressing its deprecation warning.

    ragas.metrics.collections is the new import path, but its metrics take a
    different constructor shape (an InstructorBaseRagasLLM plus, for some
    metrics, a separate embeddings object) than the RagasJudge adapter this
    module builds. Migrating requires a real adapter rewrite that needs a live
    ragas run to verify — tracked as follow-up work, not done blind here.
    """
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            import ragas.metrics as ragas_metrics_module

            return getattr(ragas_metrics_module, name)
    except ImportError as exc:
        raise ImportError("ragas is required. Install with: uv sync --extra semantic") from exc


def make_faithfulness(judge: ProviderJudge, threshold: float = THRESHOLD_FAITHFULNESS) -> Any:
    """RAGAS Faithfulness — detects hallucination, stale context, injection compliance.

    Primary targets: defect #1 (bariatric hallucination), defect #2 (stale premium),
    defect #7 (injection compliance language not grounded in authoritative corpus).
    """
    ensure_ragas_compat()
    faithfulness_cls = _import_ragas_metric_class("Faithfulness")
    metric = faithfulness_cls()
    metric.llm = _ragas_judge(judge)
    return metric


def make_context_precision(
    judge: ProviderJudge, threshold: float = THRESHOLD_CONTEXT_PRECISION
) -> Any:
    """RAGAS ContextPrecision — measures retrieval precision (relevant chunks retrieved)."""
    ensure_ragas_compat()
    context_precision_cls = _import_ragas_metric_class("ContextPrecision")
    metric = context_precision_cls()
    metric.llm = _ragas_judge(judge)
    return metric


def make_context_recall(judge: ProviderJudge, threshold: float = THRESHOLD_CONTEXT_RECALL) -> Any:
    """RAGAS ContextRecall — measures whether required supporting context was retrieved."""
    ensure_ragas_compat()
    context_recall_cls = _import_ragas_metric_class("ContextRecall")
    metric = context_recall_cls()
    metric.llm = _ragas_judge(judge)
    return metric


def make_ragas_answer_relevancy(
    judge: ProviderJudge, threshold: float = THRESHOLD_ANSWER_RELEVANCY
) -> Any:
    """RAGAS AnswerRelevancy — penalizes incomplete or off-topic answers."""
    ensure_ragas_compat()
    answer_relevancy_cls = _import_ragas_metric_class("AnswerRelevancy")
    metric = answer_relevancy_cls()
    metric.llm = _ragas_judge(judge)
    return metric
