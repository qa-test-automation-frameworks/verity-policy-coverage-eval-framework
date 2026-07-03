"""Tier-1: retrieval quality gates against the real PolicyRetriever.

test_retrieval_benchmark.py scores FixtureRetriever — pre-authored chunk
lists that never exercise PolicyRetriever's actual chunking + embedding path.
This module runs the same benchmark expectations against the real retriever,
backed by an isolated temp Chroma index, so a chunking/ranking regression
that only manifests in the real embedding path is caught by Tier-1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sut.retriever import Retriever
from tests.deterministic.retrieval_contract import assert_retriever_supports_benchmark
from verity.config import RetrievalConfig
from verity.retrieval_eval import RetrievalBenchmark, load_retrieval_benchmarks

pytestmark = pytest.mark.deterministic

_BENCHMARKS = load_retrieval_benchmarks(Path("datasets/retrieval/benchmarks.yaml"))


@pytest.fixture(scope="module")
def real_retriever(tmp_path_factory: pytest.TempPathFactory) -> Retriever:
    """A PolicyRetriever backed by a throwaway Chroma index for this test module."""
    from sut.retriever import PolicyRetriever

    persist_dir = tmp_path_factory.mktemp("chroma-quality")
    config = RetrievalConfig(persist_dir=persist_dir)
    retriever = PolicyRetriever(config)
    try:
        retriever.index_corpus()
    except Exception as exc:  # pragma: no cover - depends on local network/cache state
        pytest.skip(f"Could not initialize the real embedding retriever: {exc}")
    return retriever


@pytest.mark.needs_onnx_download
@pytest.mark.parametrize("benchmark", _BENCHMARKS, ids=[b.case_id for b in _BENCHMARKS])
def test_real_retrieval_supports_expected_evidence(
    benchmark: RetrievalBenchmark, real_retriever: Retriever
) -> None:
    assert_retriever_supports_benchmark(real_retriever, benchmark, enforce_no_answer=True)
