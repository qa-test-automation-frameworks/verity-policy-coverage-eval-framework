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

from verity.config import RetrievalConfig
from verity.retrieval_eval import RetrievalBenchmark, load_retrieval_benchmarks, score_retrieval

pytestmark = pytest.mark.deterministic

_BENCHMARKS = load_retrieval_benchmarks(Path("datasets/retrieval/benchmarks.yaml"))

# ctrl-missing-acupuncture-policy has no lexical or semantic signal to key off
# of at all — the corpus never mentions acupuncture, so embedding distances
# for every chunk cluster tightly together with no distinguishing overlap.
# Real-embedding ranking of a "the corpus is silent on this" query is a much
# harder problem than section/keyword-matched retrieval; the equivalent
# FixtureRetriever benchmark in test_retrieval_benchmark.py still gates this
# case deterministically. Tracked as a known gap rather than tuned away.
_KNOWN_HARD_CASES = {"ctrl-missing-acupuncture-policy"}


@pytest.fixture(scope="module")
def real_retriever(tmp_path_factory: pytest.TempPathFactory) -> object:
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
    benchmark: RetrievalBenchmark, real_retriever: object
) -> None:
    if benchmark.case_id in _KNOWN_HARD_CASES:
        pytest.xfail(
            f"KI-1: {benchmark.case_id} has no lexical/semantic signal in the real corpus "
            "(see docs/known-issues.md)"
        )
    chunks = real_retriever.retrieve(benchmark.query)  # type: ignore[attr-defined]
    score = score_retrieval(chunks, benchmark)
    assert score.passed, score.message
