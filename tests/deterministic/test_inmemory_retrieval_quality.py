"""Tier-1: retrieval quality gates against InMemoryCosineRetriever.

Runs the same benchmark contract as test_real_retrieval_quality.py and
test_retrieval_benchmark.py, against a third Retriever implementation that
stores embeddings in a numpy array and ranks by brute-force cosine similarity
instead of Chroma's index — proving the protocol seam holds across storage
mechanisms, not just across PolicyRetriever and the fixture stub.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sut.retriever import Retriever
from tests.deterministic.retrieval_contract import assert_retriever_supports_benchmark
from verity.retrieval_eval import RetrievalBenchmark, load_retrieval_benchmarks

pytestmark = pytest.mark.deterministic

_BENCHMARKS = load_retrieval_benchmarks(Path("datasets/retrieval/benchmarks.yaml"))


@pytest.fixture(scope="module")
def inmemory_retriever() -> Retriever:
    """An InMemoryCosineRetriever indexed against the real corpus."""
    from sut.retriever import InMemoryCosineRetriever

    retriever = InMemoryCosineRetriever()
    try:
        retriever.index_corpus()
    except Exception as exc:  # pragma: no cover - depends on local network/cache state
        pytest.skip(f"Could not initialize the in-memory embedding retriever: {exc}")
    return retriever


@pytest.mark.needs_onnx_download
@pytest.mark.parametrize("benchmark", _BENCHMARKS, ids=[b.case_id for b in _BENCHMARKS])
def test_inmemory_retrieval_supports_expected_evidence(
    benchmark: RetrievalBenchmark, inmemory_retriever: Retriever
) -> None:
    assert_retriever_supports_benchmark(inmemory_retriever, benchmark, enforce_no_answer=True)
