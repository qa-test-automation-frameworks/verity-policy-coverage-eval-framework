"""Unit tests for retrieval benchmark scoring."""

from __future__ import annotations

from pathlib import Path

from sut.retriever import Chunk
from verity.retrieval_eval import RetrievalBenchmark, load_retrieval_benchmarks, score_retrieval


def test_load_retrieval_benchmarks() -> None:
    benchmarks = load_retrieval_benchmarks(Path("datasets/retrieval/benchmarks.yaml"))
    assert benchmarks
    assert all(item.case_id for item in benchmarks)


def test_score_retrieval_passes_when_sources_and_terms_match() -> None:
    benchmark = RetrievalBenchmark(
        case_id="case",
        query="q",
        expected_sources=["policy.md"],
        required_terms=["covered"],
        min_source_precision=1.0,
    )
    chunks = [
        Chunk(text="This service is covered.", source="policy.md", section="§1", chunk_id="1")
    ]

    score = score_retrieval(chunks, benchmark)

    assert score.passed
    assert score.source_recall == 1.0
    assert score.term_recall == 1.0
    assert score.source_precision == 1.0
    assert score.mrr == 1.0
    assert score.hit_at_k == 1.0
    assert score.ndcg == 1.0


def test_score_retrieval_fails_when_required_term_is_missing() -> None:
    benchmark = RetrievalBenchmark(
        case_id="case",
        query="q",
        expected_sources=["policy.md"],
        required_terms=["excluded"],
        min_source_precision=1.0,
    )
    chunks = [
        Chunk(text="This service is covered.", source="policy.md", section="§1", chunk_id="1")
    ]

    score = score_retrieval(chunks, benchmark)

    assert not score.passed
    assert score.term_recall == 0.0


def test_score_retrieval_reports_rank_aware_metrics() -> None:
    benchmark = RetrievalBenchmark(
        case_id="case",
        query="q",
        expected_sources=["policy.md"],
        required_terms=[],
        min_source_precision=0.25,
    )
    chunks = [
        Chunk(text="Distractor", source="other.md", section="§1", chunk_id="1"),
        Chunk(text="Relevant", source="policy.md", section="§2", chunk_id="2"),
        Chunk(text="Later distractor", source="extra.md", section="§3", chunk_id="3"),
    ]

    score = score_retrieval(chunks, benchmark)

    assert score.passed
    assert score.mrr == 0.5
    assert score.hit_at_k == 1.0
    assert 0.0 < score.ndcg < 1.0
    assert "mrr=0.50" in score.message


def test_score_retrieval_rank_metrics_are_zero_without_relevant_sources() -> None:
    benchmark = RetrievalBenchmark(
        case_id="case",
        query="q",
        expected_sources=["policy.md"],
        required_terms=[],
        min_source_precision=0.5,
    )
    chunks = [Chunk(text="Distractor", source="other.md", section="§1", chunk_id="1")]

    score = score_retrieval(chunks, benchmark)

    assert score.mrr == 0.0
    assert score.hit_at_k == 0.0
    assert score.ndcg == 0.0
