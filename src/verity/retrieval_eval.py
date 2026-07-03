"""Retrieval benchmark loading and scoring utilities."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from sut.retriever import Chunk


class RetrievalBenchmark(BaseModel):
    """Expected retrieval evidence for one query.

    min_source_precision is the release gate — score_retrieval.passed is False
    below it. diagnostic_threshold, when set, is a stricter aspirational target
    reported alongside the gate result but never fails a run on its own; it
    exists so a low gate threshold (tolerated noisy-context cases) doesn't read
    as an unexamined default — it flags how far the retriever is from the
    better precision this case should eventually hit.

    expected_chunk_ids, when set, is the ground-truth set of specific chunks
    (not just source files) the retriever should return for this query —
    typically sourced from a recorded snapshot of the real embedding-based
    retriever (see datasets/retrieval/recorded_chunks.json). Source-level
    recall/precision can pass while the retriever grabs the wrong section of
    the right file; chunk-level precision/recall (see RetrievalScore) is the
    finer-grained signal that catches that case. Optional and additive: empty
    by default, and score_retrieval reports None for the chunk-level fields
    rather than failing when it isn't set.

    min_chunk_precision/min_chunk_recall are the chunk-level release gates,
    analogous to min_source_precision but only meaningful (and only checked
    by RetrievalScore.chunk_passed) when expected_chunk_ids is set. They do
    not affect RetrievalScore.passed, which stays source-level-only so
    existing callers that never set expected_chunk_ids are unaffected.
    """

    case_id: str
    query: str
    expected_sources: list[str] = Field(default_factory=list)
    required_terms: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    min_source_precision: float = Field(default=0.5, ge=0.0, le=1.0)
    min_chunk_precision: float = Field(default=1.0, ge=0.0, le=1.0)
    min_chunk_recall: float = Field(default=1.0, ge=0.0, le=1.0)
    diagnostic_threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    # True for a query the corpus has no relevant section for at all (the
    # "the corpus is silent on this" case). Only meaningful to the real
    # embedding-based retriever, which returns no chunks for such a query
    # (see PolicyRetriever._MAX_RELEVANT_DISTANCE); FixtureRetriever-backed
    # tests are unaffected since their hand-authored distractor context tests
    # a different thing (how the agent reasons over "not affirmatively
    # covered" context) and continue to use expected_sources/expected_chunk_ids
    # as before.
    no_answer: bool = False


class RetrievalScore(BaseModel):
    """Objective retrieval score for a benchmark."""

    case_id: str
    source_recall: float
    term_recall: float
    source_precision: float
    mrr: float
    hit_at_k: float
    ndcg: float
    chunk_precision: float | None
    chunk_recall: float | None
    chunk_passed: bool | None  # None when expected_chunk_ids is unset — no gate to evaluate
    passed: bool
    meets_diagnostic: bool | None
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

    expected_chunk_ids = set(benchmark.expected_chunk_ids)
    chunk_precision: float | None = None
    chunk_recall: float | None = None
    chunk_passed: bool | None = None
    if expected_chunk_ids:
        retrieved_chunk_ids = {chunk.chunk_id for chunk in chunks}
        found_chunk_ids = retrieved_chunk_ids & expected_chunk_ids
        chunk_recall = len(found_chunk_ids) / len(expected_chunk_ids)
        chunk_precision = len(found_chunk_ids) / len(retrieved_chunk_ids) if chunks else 0.0
        chunk_passed = (
            chunk_precision >= benchmark.min_chunk_precision
            and chunk_recall >= benchmark.min_chunk_recall
        )

    passed = (
        source_recall == 1.0
        and term_recall == 1.0
        and source_precision >= benchmark.min_source_precision
    )
    meets_diagnostic = (
        source_precision >= benchmark.diagnostic_threshold
        if benchmark.diagnostic_threshold is not None
        else None
    )
    message = (
        f"source_recall={source_recall:.2f}, term_recall={term_recall:.2f}, "
        f"source_precision={source_precision:.2f}, mrr={mrr:.2f}, "
        f"hit_at_k={hit_at_k:.2f}, ndcg={ndcg:.2f}, sources={sorted(sources)}"
    )
    if chunk_precision is not None and chunk_recall is not None:
        message += (
            f", chunk_precision={chunk_precision:.2f}, chunk_recall={chunk_recall:.2f}, "
            f"chunk_passed={chunk_passed}"
        )
    if meets_diagnostic is False:
        message += (
            f", below diagnostic_threshold={benchmark.diagnostic_threshold:.2f} "
            "(does not fail the gate, but flags room for retriever improvement)"
        )
    return RetrievalScore(
        case_id=benchmark.case_id,
        source_recall=source_recall,
        term_recall=term_recall,
        source_precision=source_precision,
        mrr=mrr,
        hit_at_k=hit_at_k,
        ndcg=ndcg,
        chunk_precision=chunk_precision,
        chunk_recall=chunk_recall,
        chunk_passed=chunk_passed,
        passed=passed,
        meets_diagnostic=meets_diagnostic,
        message=message,
    )
