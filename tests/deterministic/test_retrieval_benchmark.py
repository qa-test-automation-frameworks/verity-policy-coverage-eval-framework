"""Tier-1 retrieval relevance benchmark checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from sut.retriever import FixtureRetriever
from verity.retrieval_eval import RetrievalBenchmark, load_retrieval_benchmarks, score_retrieval

pytestmark = pytest.mark.deterministic

_BENCHMARKS = load_retrieval_benchmarks(Path("datasets/retrieval/benchmarks.yaml"))


@pytest.mark.parametrize("benchmark", _BENCHMARKS, ids=[b.case_id for b in _BENCHMARKS])
def test_fixture_retrieval_supports_expected_evidence(benchmark: RetrievalBenchmark) -> None:
    chunks = FixtureRetriever(benchmark.case_id).retrieve(benchmark.query)
    score = score_retrieval(chunks, benchmark)
    assert score.passed, score.message


def test_retrieval_benchmark_dataset_not_empty() -> None:
    assert _BENCHMARKS
