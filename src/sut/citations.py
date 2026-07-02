"""Citation resolution: mapping a generated answer back to the retrieved
chunks that actually support it, rather than blindly citing everything the
retriever returned.

Two resolution strategies, tried in order:
1. Model-cited: parse the model's own inline "(Document §section)" markers
   and resolve them against retrieved chunks.
2. Lexical-overlap fallback: when the model didn't cite anything resolvable,
   fall back to chunks whose distinctive tokens are reflected in the answer.
"""

from __future__ import annotations

import re

from sut.retriever import Chunk

# Filters generic filler from *answer* text when matching it against retrieved
# chunk text for citation resolution. Deliberately kept separate from
# sut.retriever._QUERY_STOPWORDS, which filters *user query* terms for
# lexical-overlap retrieval scoring — different domain (answer prose vs.
# short queries), so tuning one should not silently change the other.
STOPWORDS = frozenset(
    {
        "this",
        "that",
        "with",
        "from",
        "your",
        "have",
        "will",
        "plan",
        "covers",
        "coverage",
        "member",
        "would",
        "into",
        "after",
        "before",
        "roughly",
        "estimated",
        "depending",
        "additional",
        "provisions",
        "status",
    }
)

_NUMERIC_TOKEN_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")
_WORD_TOKEN_RE = re.compile(r"[a-z]{4,}")


def significant_tokens(text: str) -> set[str]:
    """Distinctive numeric and word tokens used to detect whether a chunk's
    content is actually reflected in the final answer, so citations point to
    chunks that support the response rather than every chunk retrieved."""
    lowered = text.lower()
    numbers = set(_NUMERIC_TOKEN_RE.findall(lowered))
    words = {w for w in _WORD_TOKEN_RE.findall(lowered) if w not in STOPWORDS}
    return numbers | words


def supporting_chunks(chunks: list[Chunk], answer: str) -> list[Chunk]:
    """Filter retrieved chunks down to those whose content is reflected in the
    final answer, instead of blindly citing every chunk that was retrieved."""
    answer_tokens = significant_tokens(answer)
    if not answer_tokens:
        return []
    return [chunk for chunk in chunks if significant_tokens(chunk.text) & answer_tokens]


# The system prompt instructs the model to "cite the source document and
# section for any coverage claim you make." In practice it does so inline as
# "(<Document> §<section>)", e.g. "(Bronze §3.3)" or "(Amendment §A2)".
_MODEL_CITATION_RE = re.compile(r"\(([A-Za-z][A-Za-z ]*?)\s*§\s*([\w.]+)\)")


def model_cited_chunks(chunks: list[Chunk], answer: str) -> list[Chunk]:
    """Resolve the model's own inline citations to the chunks it actually
    retrieved, so citations reflect what the model said it used rather than
    a lexical-overlap guess. Only matches against retrieved chunks — a
    citation naming a document that wasn't retrieved resolves to nothing."""
    matched: list[Chunk] = []
    for name, _section in _MODEL_CITATION_RE.findall(answer):
        stem = name.strip().lower()
        for chunk in chunks:
            source_stem = chunk.source.removesuffix(".md").lower()
            if source_stem.startswith(stem) or stem.startswith(source_stem):
                if chunk not in matched:
                    matched.append(chunk)
                break
    return matched


def resolve_citations(chunks: list[Chunk], answer: str) -> list[Chunk]:
    """Resolve retrieved chunks that support the answer, preferring the
    model's own inline citations and falling back to lexical overlap only
    when the model didn't cite anything resolvable."""
    return model_cited_chunks(chunks, answer) or supporting_chunks(chunks, answer)
