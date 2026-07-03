"""Unit tests for the corpus chunker and FixtureRetriever (no Chroma, no embedding calls)."""

from __future__ import annotations

import json
from pathlib import Path

from chromadb.api.types import EmbeddingFunction

from sut.retriever import (
    Chunk,
    FixtureRetriever,
    _chunk_text,
    _extract_section_heading,
    _split_into_sections,
    _stable_id,
    _strip_html_comments,
)


class TestChunkText:
    def test_short_text_single_chunk(self) -> None:
        text = "Hello world. This is a test."
        chunks = _chunk_text(text, chunk_size=100, overlap=10)
        assert len(chunks) == 1
        assert "Hello world" in chunks[0]

    def test_long_text_splits_at_paragraph(self) -> None:
        para = "word " * 60  # 60-word paragraph
        text = para + "\n\n" + para
        chunks = _chunk_text(text, chunk_size=50, overlap=10)
        assert len(chunks) >= 2

    def test_overlap_not_negative_chunks(self) -> None:
        text = "\n\n".join(["word " * 10 for _ in range(20)])
        chunks = _chunk_text(text, chunk_size=30, overlap=5)
        assert all(len(c) > 0 for c in chunks)

    def test_empty_text_returns_empty(self) -> None:
        assert _chunk_text("", chunk_size=100, overlap=10) == []


class TestStripHtmlComments:
    def test_removes_single_line_comment(self) -> None:
        text = "Covered text\n<!-- internal note -->\nMore policy text"
        assert _strip_html_comments(text) == "Covered text\n\nMore policy text"

    def test_removes_multiline_comment(self) -> None:
        text = "Before\n<!-- line one\nline two -->\nAfter"
        assert "line one" not in _strip_html_comments(text)


class TestSplitIntoSections:
    def test_no_headings_returns_single_untitled_section(self) -> None:
        text = "Just some plain text with no headings at all."
        sections = _split_into_sections(text)
        assert sections == [("", text)]

    def test_single_heading_captures_body(self) -> None:
        text = "# Bronze Plan\n\nBronze plan details here."
        sections = _split_into_sections(text)
        assert len(sections) == 1
        heading, body = sections[0]
        assert heading == "Bronze Plan"
        assert "Bronze plan details" in body

    def test_multiple_headings_split_at_boundaries(self) -> None:
        text = (
            "# Overview\n\nGeneral info.\n\n"
            "## Preventive Care\n\nPreventive details.\n\n"
            "## Medical Benefits\n\nMedical details."
        )
        sections = _split_into_sections(text)
        headings = [h for h, _ in sections]
        assert headings == ["Overview", "Preventive Care", "Medical Benefits"]
        # Each section's body must not leak content from a different section.
        for heading, body in sections:
            if heading == "Overview":
                assert "Preventive details" not in body
                assert "Medical details" not in body
            elif heading == "Preventive Care":
                assert "General info" not in body
                assert "Medical details" not in body
            elif heading == "Medical Benefits":
                assert "General info" not in body
                assert "Preventive details" not in body

    def test_preamble_before_first_heading_is_kept(self) -> None:
        text = "Some intro text before any heading.\n\n# First Section\n\nBody text."
        sections = _split_into_sections(text)
        assert len(sections) == 1
        _, body = sections[0]
        assert "Some intro text" in body
        assert "Body text" in body

    def test_nested_heading_levels_each_start_a_section(self) -> None:
        text = "# Top\n\nTop body.\n\n### Deep Subsection\n\nDeep body."
        sections = _split_into_sections(text)
        headings = [h for h, _ in sections]
        assert headings == ["Top", "Deep Subsection"]


class TestExtractSectionHeading:
    def test_h1_heading(self) -> None:
        text = "# Bronze Plan\n\nSome content here."
        assert _extract_section_heading(text) == "Bronze Plan"

    def test_h2_heading(self) -> None:
        text = "## §3. Medical Benefits\n\nSome content."
        assert _extract_section_heading(text) == "§3. Medical Benefits"

    def test_no_heading_returns_empty(self) -> None:
        text = "Just plain text with no heading."
        assert _extract_section_heading(text) == ""

    def test_heading_in_middle_detected(self) -> None:
        text = "Some intro text.\n\n## Middle Heading\n\nMore text."
        assert _extract_section_heading(text) == "Middle Heading"


class TestStableId:
    def test_deterministic(self) -> None:
        id1 = _stable_id("bronze.md", "some text")
        id2 = _stable_id("bronze.md", "some text")
        assert id1 == id2

    def test_different_inputs_different_ids(self) -> None:
        id1 = _stable_id("bronze.md", "text A")
        id2 = _stable_id("bronze.md", "text B")
        assert id1 != id2

    def test_source_matters(self) -> None:
        id1 = _stable_id("bronze.md", "text")
        id2 = _stable_id("silver.md", "text")
        assert id1 != id2


class TestFixtureRetriever:
    def test_returns_empty_for_missing_fixture(self, tmp_path: Path) -> None:
        r = FixtureRetriever("no-such-case", fixture_dir=tmp_path)
        assert r.retrieve("anything") == []

    def test_loads_chunks_from_json(self, tmp_path: Path) -> None:
        fixture = [
            {
                "text": "## §3.2 Specialist Visits\n- $60 copay",
                "source": "silver.md",
                "section": "§3.2 Specialist Visits",
                "chunk_id": "fx-test-01",
            }
        ]
        (tmp_path / "my-case.json").write_text(json.dumps(fixture))

        r = FixtureRetriever("my-case", fixture_dir=tmp_path)
        chunks = r.retrieve("specialist copay")
        assert len(chunks) == 1
        assert chunks[0].source == "silver.md"
        assert chunks[0].section == "§3.2 Specialist Visits"
        assert "60 copay" in chunks[0].text

    def test_returns_chunk_dataclass(self, tmp_path: Path) -> None:
        fixture = [{"text": "some text", "source": "gold.md", "section": "§1"}]
        (tmp_path / "c.json").write_text(json.dumps(fixture))
        chunks = FixtureRetriever("c", fixture_dir=tmp_path).retrieve("q")
        assert isinstance(chunks[0], Chunk)

    def test_index_corpus_is_noop(self, tmp_path: Path) -> None:
        r = FixtureRetriever("x", fixture_dir=tmp_path)
        assert r.index_corpus() == 0
        assert r.index_corpus(force=True) == 0

    def test_query_ignored_returns_all_fixtures(self, tmp_path: Path) -> None:
        fixture = [
            {"text": "chunk one", "source": "a.md", "section": "§1"},
            {"text": "chunk two", "source": "b.md", "section": "§2"},
        ]
        (tmp_path / "multi.json").write_text(json.dumps(fixture))
        r = FixtureRetriever("multi", fixture_dir=tmp_path)
        assert len(r.retrieve("irrelevant query")) == 2

    def test_chunk_id_auto_generated_when_missing(self, tmp_path: Path) -> None:
        fixture = [{"text": "text without id", "source": "x.md"}]
        (tmp_path / "noid.json").write_text(json.dumps(fixture))
        chunks = FixtureRetriever("noid", fixture_dir=tmp_path).retrieve("q")
        assert chunks[0].chunk_id  # non-empty auto-generated id

    def test_real_fixture_dir_contains_all_case_fixtures(self) -> None:
        from verity.golden import load_golden

        fixture_dir = Path("datasets/cassettes/retrieval")
        cases = load_golden()
        missing = [c.id for c in cases if not (fixture_dir / f"{c.id}.json").exists()]
        assert not missing, f"Missing retrieval fixtures for cases: {missing}"


class TestCorpusFingerprint:
    """PolicyRetriever detects a changed corpus and rebuilds its index rather
    than silently continuing to serve stale embeddings."""

    def _make_corpus(self, tmp_path: Path, text: str) -> Path:
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        (corpus_dir / "policy.md").write_text(text)
        return corpus_dir

    def test_fingerprint_empty_before_indexing(self, tmp_path: Path) -> None:
        from sut.retriever import PolicyRetriever
        from verity.config import RetrievalConfig

        corpus_dir = self._make_corpus(tmp_path, "# Title\n\n## §1\nOriginal content.")
        config = RetrievalConfig(persist_dir=tmp_path / "chroma", corpus_dir=corpus_dir)
        retriever = PolicyRetriever(config)
        assert retriever.corpus_fingerprint() == ""

    def test_fingerprint_set_after_indexing(self, tmp_path: Path) -> None:
        from sut.retriever import PolicyRetriever
        from verity.config import RetrievalConfig

        corpus_dir = self._make_corpus(tmp_path, "# Title\n\n## §1\nOriginal content.")
        config = RetrievalConfig(persist_dir=tmp_path / "chroma", corpus_dir=corpus_dir)
        retriever = PolicyRetriever(config)
        retriever.index_corpus()
        assert retriever.corpus_fingerprint() != ""

    def test_reindex_skipped_when_corpus_unchanged(self, tmp_path: Path) -> None:
        from sut.retriever import PolicyRetriever
        from verity.config import RetrievalConfig

        corpus_dir = self._make_corpus(tmp_path, "# Title\n\n## §1\nOriginal content.")
        config = RetrievalConfig(persist_dir=tmp_path / "chroma", corpus_dir=corpus_dir)
        retriever = PolicyRetriever(config)
        first = retriever.index_corpus()
        second = retriever.index_corpus()
        assert first > 0
        assert second == 0  # no-op: fingerprint unchanged

    def test_reindex_triggered_when_corpus_content_changes(self, tmp_path: Path) -> None:
        from sut.retriever import PolicyRetriever
        from verity.config import RetrievalConfig

        corpus_dir = self._make_corpus(tmp_path, "# Title\n\n## §1\nOriginal content.")
        config = RetrievalConfig(persist_dir=tmp_path / "chroma", corpus_dir=corpus_dir)
        retriever = PolicyRetriever(config)
        retriever.index_corpus()
        fingerprint_before = retriever.corpus_fingerprint()

        (corpus_dir / "policy.md").write_text("# Title\n\n## §1\nChanged content entirely.")
        added = retriever.index_corpus()

        assert added > 0
        assert retriever.corpus_fingerprint() != fingerprint_before

    def test_retrieved_chunks_carry_matching_corpus_fingerprint(self, tmp_path: Path) -> None:
        from sut.retriever import PolicyRetriever
        from verity.config import RetrievalConfig

        corpus_dir = self._make_corpus(tmp_path, "# Title\n\n## §1\nSome policy content here.")
        config = RetrievalConfig(persist_dir=tmp_path / "chroma", corpus_dir=corpus_dir)
        retriever = PolicyRetriever(config)
        retriever.index_corpus()

        chunks = retriever.retrieve("policy content")
        assert chunks
        assert all(c.corpus_fingerprint == retriever.corpus_fingerprint() for c in chunks)

    def test_retrieved_chunks_have_rank_and_score(self, tmp_path: Path) -> None:
        from sut.retriever import PolicyRetriever
        from verity.config import RetrievalConfig

        corpus_dir = self._make_corpus(tmp_path, "# Title\n\n## §1\nSome policy content here.")
        config = RetrievalConfig(persist_dir=tmp_path / "chroma", corpus_dir=corpus_dir)
        retriever = PolicyRetriever(config)
        retriever.index_corpus()

        chunks = retriever.retrieve("policy content")
        ranks = [c.rank for c in chunks]
        assert ranks == sorted(ranks)
        assert ranks[0] == 1
        assert all(isinstance(c.score, float) for c in chunks)


class TestInjectableEmbeddingFunction:
    """Both real retriever backends accept a custom embedding_fn instead of
    always constructing Chroma's default ONNX model — proven here with a fake
    embedder so the test stays hermetic (no ONNX download, no real vectors)."""

    class _FakeEmbeddingFn(EmbeddingFunction):  # type: ignore[type-arg]
        """Deterministic stand-in: embeds any text containing "match" as
        [1.0, 0.0] and everything else as [0.0, 1.0], so a query for "match"
        provably ranks the "match" documents first via this fake, not via any
        real semantic similarity. Subclasses Chroma's EmbeddingFunction
        protocol class so PolicyRetriever's Chroma collection accepts it as a
        custom embedding function (name(), embed_query(), etc. come from the
        base class; only __call__ needs overriding)."""

        def __init__(self) -> None:
            pass

        def __call__(self, input: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] if "match" in t else [0.0, 1.0] for t in input]

        def name(self) -> str:
            return "fake-test-embedding-fn"

        def get_config(self) -> dict[str, object]:
            return {}

    def _make_corpus(self, tmp_path: Path) -> Path:
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        (corpus_dir / "policy.md").write_text(
            "# Title\n\n## §1\nThis section should match the query.\n\n"
            "## §2\nThis section is unrelated filler content.\n"
        )
        return corpus_dir

    def test_policy_retriever_uses_injected_embedding_fn(self, tmp_path: Path) -> None:
        from sut.retriever import PolicyRetriever
        from verity.config import RetrievalConfig

        corpus_dir = self._make_corpus(tmp_path)
        config = RetrievalConfig(persist_dir=tmp_path / "chroma", corpus_dir=corpus_dir, top_k=1)
        retriever = PolicyRetriever(config, embedding_fn=self._FakeEmbeddingFn())
        retriever.index_corpus()

        chunks = retriever.retrieve("match")
        assert chunks
        assert "should match" in chunks[0].text

    def test_in_memory_retriever_uses_injected_embedding_fn(self, tmp_path: Path) -> None:
        from sut.retriever import InMemoryCosineRetriever
        from verity.config import RetrievalConfig

        corpus_dir = self._make_corpus(tmp_path)
        config = RetrievalConfig(persist_dir=tmp_path / "chroma", corpus_dir=corpus_dir, top_k=1)
        retriever = InMemoryCosineRetriever(config, embedding_fn=self._FakeEmbeddingFn())
        retriever.index_corpus()

        chunks = retriever.retrieve("match")
        assert chunks
        assert "should match" in chunks[0].text
