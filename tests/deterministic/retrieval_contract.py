"""Shared retrieval benchmark assertions for Retriever implementations."""

from __future__ import annotations

from sut.retriever import Retriever
from verity.retrieval_eval import RetrievalBenchmark, score_retrieval


def assert_retriever_supports_benchmark(
    retriever: Retriever,
    benchmark: RetrievalBenchmark,
    *,
    enforce_no_answer: bool = False,
) -> None:
    chunks = retriever.retrieve(benchmark.query)
    if enforce_no_answer and benchmark.no_answer:
        assert chunks == [], (
            f"{benchmark.case_id} expected no relevant chunks but got: "
            f"{[(c.source, c.section) for c in chunks]}"
        )
        return
    score = score_retrieval(chunks, benchmark)
    assert score.passed, score.message
