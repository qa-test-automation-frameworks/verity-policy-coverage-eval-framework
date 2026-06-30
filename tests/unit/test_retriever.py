"""Unit tests for the corpus chunker (no Chroma, no embedding calls)."""

from __future__ import annotations

from sut.retriever import _chunk_text, _extract_section_heading, _stable_id


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
