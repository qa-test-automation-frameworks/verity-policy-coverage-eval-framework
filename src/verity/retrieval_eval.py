"""Retrieval benchmark loading and scoring utilities."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from sut.retriever import Chunk


class RetrievalBenchmark(BaseModel):
    """Expected retrieval evidence for one query."""

    case_id: str
    query: str
    expected_sources: list[str] = Field(default_factory=list)
    required_terms: list[str] = Field(default_factory=list)
    min_source_precision: float = Field(default=0.5, ge=0.0, le=1.0)


class RetrievalScore(BaseModel):
    """Objective retrieval score for a benchmark."""

    case_id: str
    source_recall: float
    term_recall: float
    source_precision: float
    mrr: float
    hit_at_k: float
    ndcg: float
    passed: bool
    message: str


def load_retrieval_benchmarks(
    path: Path | str = "datasets/retrieval/benchmarks.yaml",
) -> list[RetrievalBenchmark]:
    """Load retrieval benchmark expectations from YAML."""
    benchmark_path = Path(path)
    with benchmark_path.open(encoding="utf-8") as fh:
        raw: Any = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        return []
    return [RetrievalBenchmark.model_validate(item) for item in raw.get("benchmarks", [])]


def score_retrieval(chunks: list[Chunk], benchmark: RetrievalBenchmark) -> RetrievalScore:
    """Score retrieved chunks against expected sources and required supporting terms."""
    sources = {chunk.source for chunk in chunks}
    expected_sources = set(benchmark.expected_sources)
    found_sources = sources & expected_sources
    source_recall = len(found_sources) / len(expected_sources) if expected_sources else 1.0

    combined = "\n".join(chunk.text for chunk in chunks).lower()
    required_terms = [term.lower() for term in benchmark.required_terms]
    found_terms = [term for term in required_terms if term in combined]
    term_recall = len(found_terms) / len(required_terms) if required_terms else 1.0

    if chunks and expected_sources:
        relevant_source_chunks = [chunk for chunk in chunks if chunk.source in expected_sources]
        source_precision = len(relevant_source_chunks) / len(chunks)
    else:
        source_precision = 1.0 if not chunks and not expected_sources else 0.0

    relevance = [1.0 if chunk.source in expected_sources else 0.0 for chunk in chunks]
    first_relevant_rank = next((idx + 1 for idx, rel in enumerate(relevance) if rel), None)
    mrr = 1.0 / first_relevant_rank if first_relevant_rank else 0.0
    hit_at_k = 1.0 if first_relevant_rank else 0.0

    dcg = sum(rel / math.log2(idx + 2) for idx, rel in enumerate(relevance))
    ideal_relevant = min(len(expected_sources), len(chunks))
    idcg = sum(1.0 / math.log2(idx + 2) for idx in range(ideal_relevant))
    ndcg = dcg / idcg if idcg else 1.0

    passed = (
        source_recall == 1.0
        and term_recall == 1.0
        and source_precision >= benchmark.min_source_precision
    )
    message = (
        f"source_recall={source_recall:.2f}, term_recall={term_recall:.2f}, "
        f"source_precision={source_precision:.2f}, mrr={mrr:.2f}, "
        f"hit_at_k={hit_at_k:.2f}, ndcg={ndcg:.2f}, sources={sorted(sources)}"
    )
    return RetrievalScore(
        case_id=benchmark.case_id,
        source_recall=source_recall,
        term_recall=term_recall,
        source_precision=source_precision,
        mrr=mrr,
        hit_at_k=hit_at_k,
        ndcg=ndcg,
        passed=passed,
        message=message,
    )
