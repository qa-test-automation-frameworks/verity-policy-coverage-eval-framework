"""RAG retriever: chunk policy corpus → embed → Chroma → retrieve.

Uses Chroma's built-in ONNX embedding function (all-MiniLM-L6-v2) so retrieval
is fully local and reproducible — no external embedding API calls.

The ONNX model is downloaded and cached by Chroma on first use; subsequent runs
are offline. Document this in CONTRIBUTING and cache in CI if needed (M2).

FixtureRetriever is a drop-in replacement for deterministic tests: it serves
pre-authored Chunk lists from JSON files in datasets/cassettes/retrieval/
so Tier-1 tests need no Chroma instance and no ONNX download.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from verity.config import RetrievalConfig


@dataclass(frozen=True)
class Chunk:
    """A retrieved text chunk with provenance metadata."""

    text: str
    source: str  # filename (relative to corpus_dir)
    section: str  # detected heading, or ""
    chunk_id: str  # stable hash of (source, text)


def _extract_section_heading(text: str) -> str:
    """Return the first markdown heading found in the chunk, or empty string."""
    match = re.search(r"^#{1,3}\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _strip_html_comments(text: str) -> str:
    """Remove Markdown HTML comments before chunking indexed corpus files."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks by word count (markdown-aware)."""
    # Split on paragraph boundaries first, then by size
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    current_words: list[str] = []

    for para in paragraphs:
        words = para.split()
        if not words:
            continue
        if len(current_words) + len(words) <= chunk_size:
            current_words.extend(words)
        else:
            if current_words:
                chunks.append(" ".join(current_words))
            # If the paragraph itself is larger than chunk_size, slice it
            while len(words) > chunk_size:
                chunks.append(" ".join(words[:chunk_size]))
                words = words[chunk_size - overlap :]
            current_words = words

    if current_words:
        chunks.append(" ".join(current_words))
    return chunks


_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


def _split_into_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, section_text) pairs at heading boundaries.

    Chunking by raw word count alone lets a single chunk span several unrelated
    ## / ### sections (e.g. "Overview" + "Preventive Care" + "Medical Benefits"
    merged together), which dilutes embedding similarity and hurts retrieval
    precision. Splitting at heading boundaries first keeps each chunk scoped to
    one topic; oversized sections are still size-split by _chunk_text.
    """
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [("", text)]

    sections: list[tuple[str, str]] = []
    preamble = text[: matches[0].start()].strip()
    for i, m in enumerate(matches):
        heading_text = m.group(2).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        if i == 0 and preamble:
            body = preamble + "\n\n" + body
        sections.append((heading_text, body))
    return sections


def _stable_id(source: str, text: str) -> str:
    return hashlib.sha256(f"{source}||{text}".encode()).hexdigest()[:16]


_PLAN_TIER_NAMES = ("bronze", "silver", "gold")
_DISTANCE_MARGIN = 0.20


def _mentioned_plan(query: str) -> str | None:
    """Return the single plan tier named in the query, or None if zero or several are named."""
    lowered = query.lower()
    mentioned = [name for name in _PLAN_TIER_NAMES if name in lowered]
    return mentioned[0] if len(mentioned) == 1 else None


def _plan_scoped_source(source: str, plan: str) -> bool:
    """True if a chunk's source is either plan-agnostic or belongs to the named plan tier."""
    stem = source.lower().removesuffix(".md")
    return stem not in _PLAN_TIER_NAMES or stem == plan


_QUERY_STOPWORDS = frozenset(
    {
        "what",
        "does",
        "is",
        "are",
        "for",
        "the",
        "and",
        "my",
        "of",
        "a",
        "an",
        "to",
        "do",
        "how",
        "many",
        "on",
        "in",
        "under",
        "or",
        "with",
        "plan",
        "cover",
        "covers",
        "covered",
        "this",
        "that",
        "you",
        "your",
        "i",
    }
)
_LEXICAL_WEIGHT = 0.5


def _keyword_overlap_bonus(query: str, text: str) -> float:
    """Fraction of distinctive query terms literally present in a chunk's text.

    A pure embedding-similarity ranking treats sections with parallel
    boilerplate structure (e.g. every plan's own "Prior Authorization"
    mention) as near-equidistant from a query that names a specific
    requirement. Boosting chunks that literally contain the query's
    distinctive terms recovers exact-match evidence (e.g. a query about
    "prior authorization" should rank the corpus's dedicated Prior
    Authorization section highly) without abandoning semantic search.
    """
    query_terms = {w for w in re.findall(r"[a-z']{3,}", query.lower()) if w not in _QUERY_STOPWORDS}
    if not query_terms:
        return 0.0
    lowered = text.lower()
    hits = sum(1 for term in query_terms if term in lowered)
    return hits / len(query_terms)


class PolicyRetriever:
    """Embeds the corpus into Chroma and retrieves relevant chunks for a query."""

    _COLLECTION_NAME = "policy_corpus"

    def __init__(self, config: RetrievalConfig | None = None) -> None:
        self._config = config or RetrievalConfig()
        self._embedding_fn: Any = DefaultEmbeddingFunction()
        self._client: Any = None
        self._collection: Any = None

    def _get_collection(self) -> Any:
        if self._collection is not None:
            return self._collection
        persist_path = str(self._config.persist_dir)
        self._client = chromadb.PersistentClient(path=persist_path)
        self._collection = self._client.get_or_create_collection(
            name=self._COLLECTION_NAME,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        return self._collection

    def index_corpus(self, force: bool = False) -> int:
        """Chunk and embed all markdown files in corpus_dir. Returns chunks added."""
        collection = self._get_collection()
        corpus_dir = self._config.corpus_dir

        if not corpus_dir.is_dir():
            raise FileNotFoundError(f"Corpus directory not found: {corpus_dir}")

        md_files = sorted(corpus_dir.glob("*.md"))
        if not md_files:
            raise FileNotFoundError(f"No markdown files found in {corpus_dir}")

        if not force and collection.count() > 0:
            return 0  # already indexed

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, str]] = []

        for md_file in md_files:
            raw = _strip_html_comments(md_file.read_text(encoding="utf-8"))
            title_match = re.match(r"^#\s+(.+)$", raw, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else md_file.stem

            for heading, section_text in _split_into_sections(raw):
                # Prepend the document title so each chunk's embedding retains which
                # plan it belongs to — sections with parallel structure across plan
                # tiers (e.g. "§4. Prescription Drugs") would otherwise be
                # indistinguishable once split out on their own.
                titled_text = f"{title}\n\n{section_text}"
                sub_chunks = _chunk_text(
                    titled_text, self._config.chunk_size, self._config.chunk_overlap
                )
                for chunk_text in sub_chunks:
                    chunk_id = _stable_id(md_file.name, chunk_text)
                    section = heading or _extract_section_heading(chunk_text)
                    ids.append(chunk_id)
                    documents.append(chunk_text)
                    metadatas.append({"source": md_file.name, "section": section})

        if ids:
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

        return len(ids)

    def retrieve(self, query: str, top_k: int | None = None) -> list[Chunk]:
        """Return the top-k most relevant chunks for the given query.

        Two refinements beyond a plain top-k similarity query, both aimed at
        precision (not returning chunks that merely resemble the query in
        boilerplate structure):

        - Plan-tier query matching: if the query names exactly one plan tier
          (e.g. "Gold"), chunks from the *other* plan tiers' documents are
          dropped, since parallel section structure across plan docs
          (matching headings, similar boilerplate) otherwise makes them
          nearly indistinguishable to the embedding model.
        - Distance-margin ranking: candidates far behind the best match are
          dropped rather than padding the result out to top_k regardless of
          relevance.
        """
        k = top_k if top_k is not None else self._config.top_k
        collection = self._get_collection()

        if collection.count() == 0:
            self.index_corpus()

        # Fetch the whole collection rather than a small top-N slice: with a
        # corpus this size the cost is negligible, and truncating the ANN
        # candidate pool before re-ranking makes the margin cutoff below
        # sensitive to tiny embedding-order jitter near the truncation boundary.
        fetch_n = collection.count()
        results = collection.query(
            query_texts=[query],
            n_results=fetch_n,
            include=["documents", "metadatas", "distances"],
        )

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]

        # Re-rank by embedding distance adjusted with a lexical overlap bonus,
        # then apply plan-tier scoping and a distance-margin cutoff.
        candidates = [
            (doc, meta, dist - _LEXICAL_WEIGHT * _keyword_overlap_bonus(query, doc))
            for doc, meta, dist in zip(docs, metas, distances, strict=True)
        ]
        candidates.sort(key=lambda c: c[2])

        plan = _mentioned_plan(query)
        if plan:
            candidates = [
                (doc, meta, dist)
                for doc, meta, dist in candidates
                if _plan_scoped_source(meta.get("source", ""), plan)
            ]

        if candidates:
            best = candidates[0][2]
            candidates = [c for c in candidates if c[2] <= best + _DISTANCE_MARGIN]

        chunks: list[Chunk] = []
        for doc, meta, _dist in candidates[:k]:
            chunks.append(
                Chunk(
                    text=doc,
                    source=meta.get("source", ""),
                    section=meta.get("section", ""),
                    chunk_id=_stable_id(meta.get("source", ""), doc),
                )
            )
        return chunks


# ---------------------------------------------------------------------------
# Fixture retriever — deterministic / no Chroma required
# ---------------------------------------------------------------------------

_RETRIEVAL_FIXTURE_DIR = Path("datasets/cassettes/retrieval")


class FixtureRetriever:
    """Serves pre-authored Chunk lists from JSON fixture files.

    Drop-in replacement for PolicyRetriever in deterministic tests.
    No Chroma instance, no ONNX model download, no network required.

    Fixture files live at: datasets/cassettes/retrieval/<case_id>.json
    Each file is a JSON array of Chunk-compatible dicts.
    """

    def __init__(
        self,
        case_id: str,
        fixture_dir: Path | None = None,
    ) -> None:
        self._case_id = case_id
        self._dir = fixture_dir or _RETRIEVAL_FIXTURE_DIR

    def index_corpus(self, force: bool = False) -> int:
        return 0  # no-op — fixtures are pre-authored

    def retrieve(self, query: str, top_k: int | None = None) -> list[Chunk]:
        fixture_file = self._dir / f"{self._case_id}.json"
        if not fixture_file.exists():
            return []
        raw: Any = json.loads(fixture_file.read_text())
        return [
            Chunk(
                text=item["text"],
                source=item["source"],
                section=item.get("section", ""),
                chunk_id=item.get("chunk_id", _stable_id(item["source"], item["text"])),
            )
            for item in raw
        ]
