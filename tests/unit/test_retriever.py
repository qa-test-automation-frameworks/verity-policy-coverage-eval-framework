"""Unit tests for the corpus chunker and FixtureRetriever (no Chroma, no embedding calls)."""

from __future__ import annotations

import json
from pathlib import Path

from sut.retriever import Chunk, FixtureRetriever, _chunk_text, _extract_section_heading, _stable_id


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
