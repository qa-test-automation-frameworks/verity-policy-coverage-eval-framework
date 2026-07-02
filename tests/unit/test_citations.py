"""Unit tests for citation resolution (src/sut/citations.py)."""

from __future__ import annotations

from sut.citations import (
    model_cited_chunks,
    resolve_citations,
    significant_tokens,
    supporting_chunks,
)
from sut.retriever import Chunk


def _chunk(source: str, text: str, section: str = "") -> Chunk:
    return Chunk(text=text, source=source, section=section, chunk_id=f"id-{source}-{text[:8]}")


class TestSignificantTokens:
    def test_extracts_numbers_and_distinctive_words(self) -> None:
        tokens = significant_tokens("The Silver plan deductible is $2,000 for coinsurance.")
        assert "$2,000" in tokens
        assert "silver" in tokens
        assert "deductible" in tokens

    def test_stopwords_excluded(self) -> None:
        tokens = significant_tokens("This plan covers your member coverage after roughly status")
        assert not tokens & {"this", "plan", "covers", "your", "member", "coverage"}

    def test_empty_text_returns_empty_set(self) -> None:
        assert significant_tokens("") == set()


class TestSupportingChunks:
    def test_chunk_with_overlapping_tokens_included(self) -> None:
        chunks = [_chunk("silver.md", "Silver deductible is $2,000 annually.")]
        result = supporting_chunks(chunks, "The Silver plan deductible is $2,000.")
        assert result == chunks

    def test_chunk_with_no_overlap_excluded(self) -> None:
        chunks = [_chunk("gold.md", "Gold specialty drug coinsurance is 10 percent.")]
        result = supporting_chunks(chunks, "The Silver plan deductible is $2,000.")
        assert result == []

    def test_empty_answer_tokens_returns_empty(self) -> None:
        chunks = [_chunk("silver.md", "Silver deductible is $2,000 annually.")]
        assert supporting_chunks(chunks, "") == []


class TestModelCitedChunks:
    def test_resolves_inline_citation_to_matching_chunk(self) -> None:
        chunks = [_chunk("bronze.md", "Bronze surgical benefits.")]
        answer = "This is covered per your plan (Bronze §3.3)."
        assert model_cited_chunks(chunks, answer) == chunks

    def test_citation_naming_unretrieved_document_resolves_to_nothing(self) -> None:
        chunks = [_chunk("bronze.md", "Bronze surgical benefits.")]
        answer = "This is covered per your plan (Silver §3.3)."
        assert model_cited_chunks(chunks, answer) == []

    def test_no_citation_marker_returns_empty(self) -> None:
        chunks = [_chunk("bronze.md", "Bronze surgical benefits.")]
        assert model_cited_chunks(chunks, "No citation here.") == []


class TestResolveCitations:
    def test_prefers_model_citation_over_lexical_overlap(self) -> None:
        bronze = _chunk("bronze.md", "Bronze deductible is $4,000.")
        silver = _chunk("silver.md", "Silver deductible is $2,000.")
        answer = "Your deductible is $2,000 (Bronze §1)."
        # Lexical overlap would favor silver ($2,000 appears), but the model's
        # own citation names Bronze — resolve_citations must prefer that.
        assert resolve_citations([bronze, silver], answer) == [bronze]

    def test_falls_back_to_lexical_overlap_when_no_model_citation(self) -> None:
        chunks = [_chunk("silver.md", "Silver deductible is $2,000 annually.")]
        answer = "The Silver plan deductible is $2,000."
        assert resolve_citations(chunks, answer) == chunks
