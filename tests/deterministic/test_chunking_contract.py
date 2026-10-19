"""Tier-1: chunk metadata contract for the real corpus, indexed for real.

Unlike test_retriever_regression.py and test_real_retrieval_quality.py (which
score retrieval against benchmark queries), this asserts properties every
stored chunk must hold regardless of query: stable non-empty IDs, valid
source filenames, non-empty text, and full corpus coverage. A regression in
chunking that doesn't happen to break a benchmark query would still fail here.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from verity.config import RetrievalConfig

pytestmark = pytest.mark.deterministic

_CORPUS_DIR = Path("src/sut/corpus")


@pytest.fixture(scope="module")
def indexed_collection(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[object]]:
    """Index the corpus into a throwaway SQLite store and return raw chunk records."""
    from sut.retriever import PolicyRetriever

    persist_dir = tmp_path_factory.mktemp("sqlite-chunking-contract")
    config = RetrievalConfig(persist_dir=persist_dir)
    retriever = PolicyRetriever(config)
    added = retriever.index_corpus()
    assert added > 0

    with sqlite3.connect(f"file:{persist_dir / 'policy-index.sqlite3'}?mode=ro", uri=True) as db:
        rows = db.execute(
            "SELECT chunk_id, document, chunk_metadata FROM chunks ORDER BY ordinal"
        ).fetchall()
    return {
        "ids": [row[0] for row in rows],
        "documents": [row[1] for row in rows],
        "metadatas": [json.loads(row[2]) for row in rows],
    }


class TestChunkMetadataContract:
    def test_every_chunk_id_is_present_and_unique(
        self, indexed_collection: dict[str, list[object]]
    ) -> None:
        ids = indexed_collection["ids"]
        assert ids
        assert len(ids) == len(set(ids)), "duplicate chunk_id in the index"
        for chunk_id in ids:
            assert isinstance(chunk_id, str)
            assert len(chunk_id) == 16, f"unexpected chunk_id length: {chunk_id!r}"

    def test_every_chunk_has_a_real_corpus_source(
        self, indexed_collection: dict[str, list[object]]
    ) -> None:
        corpus_files = {p.name for p in _CORPUS_DIR.glob("*.md")}
        metadatas = indexed_collection["metadatas"]
        assert metadatas
        for meta in metadatas:
            assert isinstance(meta, dict)
            source = meta.get("source")
            assert source in corpus_files, f"chunk source {source!r} not a real corpus file"

    def test_every_chunk_has_non_empty_text(
        self, indexed_collection: dict[str, list[object]]
    ) -> None:
        documents = indexed_collection["documents"]
        assert documents
        for doc in documents:
            assert isinstance(doc, str)
            assert doc.strip(), "empty chunk text"

    def test_every_corpus_file_contributes_at_least_one_chunk(
        self, indexed_collection: dict[str, list[object]]
    ) -> None:
        corpus_files = {p.name for p in _CORPUS_DIR.glob("*.md")}
        sources_seen = {meta["source"] for meta in indexed_collection["metadatas"]}
        missing = corpus_files - sources_seen
        assert not missing, f"corpus file(s) produced zero chunks: {missing}"

    def test_section_metadata_present_for_headed_documents(
        self, indexed_collection: dict[str, list[object]]
    ) -> None:
        # Every corpus document in this repo uses markdown headings, so every
        # chunk should resolve a non-empty section (either from the
        # heading-boundary split or the fallback in-chunk heading scan).
        metadatas = indexed_collection["metadatas"]
        empty_section = [m for m in metadatas if not m.get("section")]
        assert not empty_section, f"{len(empty_section)} chunk(s) have no section heading"

    def test_reindexing_without_force_produces_identical_chunk_ids(
        self, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        """Chunk IDs must be stable across index runs so citations/evidence
        referencing a chunk_id keep resolving after a routine re-index."""
        from sut.retriever import PolicyRetriever

        persist_dir = tmp_path_factory.mktemp("sqlite-chunking-stability")
        config = RetrievalConfig(persist_dir=persist_dir)

        retriever_a = PolicyRetriever(config)
        retriever_a.index_corpus()
        with sqlite3.connect(persist_dir / "policy-index.sqlite3") as db:
            ids_a = {row[0] for row in db.execute("SELECT chunk_id FROM chunks")}

        retriever_b = PolicyRetriever(config)
        assert retriever_b.index_corpus() == 0
        with sqlite3.connect(persist_dir / "policy-index.sqlite3") as db:
            ids_b = {row[0] for row in db.execute("SELECT chunk_id FROM chunks")}

        assert ids_a == ids_b
