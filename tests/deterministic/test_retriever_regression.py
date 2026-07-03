"""Tier-1: regression test against the real embedding-based retriever.

Every other Tier-1 retrieval check (test_retrieval_benchmark.py) scores
FixtureRetriever output — pre-authored chunk lists that never exercise
PolicyRetriever's actual chunking + Chroma/ONNX embedding path. That leaves
the real retriever with no committed regression coverage: a chunking or
embedding-dependency change could silently alter what gets retrieved and
nothing in the test suite would notice.

This test runs the real PolicyRetriever against the actual corpus and
compares the returned chunk IDs to a recorded snapshot
(datasets/retrieval/recorded_chunks.json). It intentionally locks in
*current* retrieval behavior rather than asserting it is high-quality —
that is a separate, larger retrieval-tuning concern. A failure here means
"retrieval changed," not necessarily "retrieval got worse"; regenerate the
snapshot deliberately when a chunking/embedding change is expected.

Embeddings are computed locally via Chroma's bundled ONNX model — no
network calls once that model is cached (see CONTRIBUTING.md). If the
model has never been downloaded on this machine and no network is
available, the test skips rather than failing the Tier-1 gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from verity.config import RetrievalConfig

pytestmark = pytest.mark.deterministic

_SNAPSHOT_PATH = Path("datasets/retrieval/recorded_chunks.json")
_RECORDED: dict[str, list[dict[str, str]]] = json.loads(_SNAPSHOT_PATH.read_text())


@pytest.fixture(scope="module")
def real_retriever(tmp_path_factory: pytest.TempPathFactory) -> object:
    """A PolicyRetriever backed by a throwaway Chroma index for this test module."""
    from sut.retriever import PolicyRetriever

    persist_dir = tmp_path_factory.mktemp("chroma-regression")
    config = RetrievalConfig(persist_dir=persist_dir)
    retriever = PolicyRetriever(config)
    try:
        retriever.index_corpus()
    except Exception as exc:  # pragma: no cover - depends on local network/cache state
        pytest.skip(f"Could not initialize the real embedding retriever: {exc}")
    return retriever


@pytest.mark.needs_onnx_download
@pytest.mark.parametrize("case_id", sorted(_RECORDED), ids=sorted(_RECORDED))
def test_real_retrieval_matches_recorded_snapshot(case_id: str, real_retriever: object) -> None:
    """The real retriever must return the same chunk IDs, in the same order, as recorded."""
    from verity.retrieval_eval import load_retrieval_benchmarks

    benchmarks = {b.case_id: b for b in load_retrieval_benchmarks()}
    benchmark = benchmarks[case_id]

    chunks = real_retriever.retrieve(benchmark.query)  # type: ignore[attr-defined]
    actual = [{"chunk_id": c.chunk_id, "source": c.source} for c in chunks]
    expected = _RECORDED[case_id]

    assert actual == expected, (
        f"Real-retriever output for {case_id!r} no longer matches the recorded snapshot. "
        "If this is an intentional chunking/embedding change, regenerate "
        "datasets/retrieval/recorded_chunks.json; otherwise this is a retrieval regression."
    )


def test_recorded_snapshot_covers_every_benchmark_case() -> None:
    from verity.retrieval_eval import load_retrieval_benchmarks

    benchmark_ids = {b.case_id for b in load_retrieval_benchmarks()}
    assert benchmark_ids == set(_RECORDED), (
        "datasets/retrieval/recorded_chunks.json is out of sync with "
        "datasets/retrieval/benchmarks.yaml — regenerate the snapshot."
    )


@pytest.mark.needs_onnx_download
@pytest.mark.parametrize("case_id", sorted(_RECORDED), ids=sorted(_RECORDED))
def test_real_retrieval_chunk_precision_recall(case_id: str, real_retriever: object) -> None:
    """Chunk-level precision/recall against the same snapshot used by the exact-
    match test above, exercising the finer-grained scoring machinery in
    verity.retrieval_eval on the real embedding-based retriever rather than only
    on FixtureRetriever's hand-authored chunks (see test_retrieval_benchmark.py,
    which only ever scores source-file-level recall/precision)."""
    from verity.retrieval_eval import load_retrieval_benchmarks, score_retrieval

    benchmarks = {b.case_id: b for b in load_retrieval_benchmarks()}
    benchmark = benchmarks[case_id]

    if benchmark.no_answer:
        pytest.skip(
            f"{case_id}: no_answer case — chunk-level precision/recall against "
            "expected_chunk_ids doesn't apply once the retriever correctly returns no "
            "chunks; see test_real_retrieval_quality.py for the no_answer assertion."
        )

    chunks = real_retriever.retrieve(benchmark.query)  # type: ignore[attr-defined]
    score = score_retrieval(chunks, benchmark)

    assert score.chunk_passed, score.message
