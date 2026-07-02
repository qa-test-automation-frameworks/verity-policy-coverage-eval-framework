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


def test_score_retrieval_meets_diagnostic_none_when_unset() -> None:
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
    assert score.meets_diagnostic is None


def test_score_retrieval_diagnostic_threshold_does_not_affect_gate() -> None:
    benchmark = RetrievalBenchmark(
        case_id="case",
        query="q",
        expected_sources=["policy.md"],
        required_terms=["covered"],
        min_source_precision=0.5,
        diagnostic_threshold=1.0,
    )
    chunks = [
        Chunk(text="This service is covered.", source="policy.md", section="§1", chunk_id="1"),
        Chunk(text="Unrelated context.", source="other.md", section="§2", chunk_id="2"),
    ]

    score = score_retrieval(chunks, benchmark)

    assert score.source_precision == 0.5
    assert score.passed  # meets the 0.5 gate
    assert score.meets_diagnostic is False  # but not the 1.0 diagnostic target
    assert "diagnostic_threshold" in score.message


def test_score_retrieval_diagnostic_threshold_met_when_precision_high_enough() -> None:
    benchmark = RetrievalBenchmark(
        case_id="case",
        query="q",
        expected_sources=["policy.md"],
        required_terms=["covered"],
        min_source_precision=0.5,
        diagnostic_threshold=1.0,
    )
    chunks = [
        Chunk(text="This service is covered.", source="policy.md", section="§1", chunk_id="1")
    ]

    score = score_retrieval(chunks, benchmark)

    assert score.meets_diagnostic is True


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


class TestChunkLevelPrecisionRecall:
    """expected_chunk_ids drives a finer-grained signal than source_recall/
    source_precision: two chunks from the same expected source file can still
    be the wrong chunk (wrong section), which source-level scoring can't see."""

    def test_none_when_expected_chunk_ids_unset(self) -> None:
        benchmark = RetrievalBenchmark(
            case_id="case", query="q", expected_sources=["policy.md"], min_source_precision=1.0
        )
        chunks = [Chunk(text="x", source="policy.md", section="§1", chunk_id="c1")]
        score = score_retrieval(chunks, benchmark)
        assert score.chunk_precision is None
        assert score.chunk_recall is None

    def test_perfect_match_scores_one(self) -> None:
        benchmark = RetrievalBenchmark(
            case_id="case",
            query="q",
            expected_sources=["policy.md"],
            expected_chunk_ids=["c1", "c2"],
            min_source_precision=1.0,
        )
        chunks = [
            Chunk(text="x", source="policy.md", section="§1", chunk_id="c1"),
            Chunk(text="y", source="policy.md", section="§2", chunk_id="c2"),
        ]
        score = score_retrieval(chunks, benchmark)
        assert score.chunk_precision == 1.0
        assert score.chunk_recall == 1.0

    def test_right_source_wrong_chunk_scores_zero(self) -> None:
        """Same source file, different section: source_precision is 1.0 but
        chunk_precision/recall correctly report a total miss."""
        benchmark = RetrievalBenchmark(
            case_id="case",
            query="q",
            expected_sources=["policy.md"],
            expected_chunk_ids=["c1"],
            min_source_precision=1.0,
        )
        chunks = [Chunk(text="wrong section", source="policy.md", section="§9", chunk_id="c9")]
        score = score_retrieval(chunks, benchmark)
        assert score.source_precision == 1.0
        assert score.chunk_precision == 0.0
        assert score.chunk_recall == 0.0

    def test_partial_overlap(self) -> None:
        benchmark = RetrievalBenchmark(
            case_id="case",
            query="q",
            expected_sources=["policy.md"],
            expected_chunk_ids=["c1", "c2"],
            min_source_precision=0.5,
        )
        chunks = [
            Chunk(text="x", source="policy.md", section="§1", chunk_id="c1"),
            Chunk(text="z", source="policy.md", section="§3", chunk_id="c3"),
        ]
        score = score_retrieval(chunks, benchmark)
        assert score.chunk_recall == 0.5  # found c1 of {c1, c2}
        assert score.chunk_precision == 0.5  # 1 of 2 retrieved chunks (c1) was expected

    def test_no_retrieved_chunks_with_expected_ids_scores_zero_precision(self) -> None:
        benchmark = RetrievalBenchmark(
            case_id="case",
            query="q",
            expected_sources=["policy.md"],
            expected_chunk_ids=["c1"],
            min_source_precision=0.0,
        )
        score = score_retrieval([], benchmark)
        assert score.chunk_recall == 0.0
        assert score.chunk_precision == 0.0

    def test_message_includes_chunk_metrics_when_set(self) -> None:
        benchmark = RetrievalBenchmark(
            case_id="case",
            query="q",
            expected_sources=["policy.md"],
            expected_chunk_ids=["c1"],
            min_source_precision=1.0,
        )
        chunks = [Chunk(text="x", source="policy.md", section="§1", chunk_id="c1")]
        score = score_retrieval(chunks, benchmark)
        assert "chunk_precision=1.00" in score.message
        assert "chunk_recall=1.00" in score.message
