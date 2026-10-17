"""RAG retrievers: chunk policy corpus → local ONNX embeddings → cosine search.

The default embedder uses FastEmbed with the Apache-2.0
``sentence-transformers/all-MiniLM-L6-v2`` model. Embeddings run locally with
ONNX Runtime and never call a hosted embedding API. PolicyRetriever stores
normalized vectors and chunk metadata in a transactional SQLite index; the
small in-memory implementation shares the same embedding and ranking path.
FixtureRetriever serves pre-authored JSON chunks for deterministic tests.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from verity.config import RetrievalConfig


class LocalOnnxEmbeddingFunction:
    """Lazy FastEmbed wrapper for the existing MiniLM model and local inference."""

    model_name = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, cache_dir: str | None = None) -> None:
        self._cache_dir = cache_dir or os.environ.get("FASTEMBED_CACHE_PATH")
        self._model: Any = None

    @property
    def model_id(self) -> str:
        return f"fastembed-{version('fastembed')}:{self.model_name}"

    def __call__(self, texts: list[str]) -> list[np.ndarray[Any, Any]]:
        if not texts:
            return []
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name, cache_dir=self._cache_dir)
        return list(self._model.embed(texts, batch_size=32))


def _embedding_identity(embedding_fn: Any) -> str:
    """Return an index-cache key that changes with the configured embedder."""
    return str(
        getattr(
            embedding_fn,
            "model_id",
            f"{type(embedding_fn).__module__}.{type(embedding_fn).__qualname__}",
        )
    )


@dataclass(frozen=True)
class Chunk:
    """A retrieved text chunk with provenance and ranking metadata for evidence payloads."""

    text: str
    source: str  # filename (relative to corpus_dir)
    section: str  # detected heading, or ""
    chunk_id: str  # stable hash of (source, text)
    rank: int = 0  # 1-based position in the returned result list
    score: float = 0.0  # retrieval distance (lower is more relevant); 0.0 for fixtures
    corpus_fingerprint: str = ""  # hash of the indexed corpus at retrieval time


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


def _corpus_fingerprint(corpus_dir: Path) -> str:
    """Hash of every corpus file's name and contents, so a stale vector index
    (built from an older version of the policy documents) can be detected and
    rebuilt rather than silently serving outdated retrieval evidence."""
    digest = hashlib.sha256()
    for md_file in sorted(corpus_dir.glob("*.md")):
        digest.update(md_file.name.encode())
        digest.update(md_file.read_bytes())
    return digest.hexdigest()[:16]


_PLAN_TIER_NAMES = ("bronze", "silver", "gold")
# Hand-tuned starting point; widening it returns more borderline candidates,
# narrowing it risks dropping a relevant chunk that scored slightly behind
# the best match. See docs/retrieval-ablation.md (make retrieval-ablation)
# for the measured pass-rate/precision curve across candidate values.
_DISTANCE_MARGIN = 0.20

# Absolute ceiling on the best (lexical-adjusted) candidate distance: when even
# the closest match is farther than this, the corpus has no section actually
# relevant to the query, and top-k should return nothing rather than padding
# the result with the least-bad irrelevant chunks. Empirically, queries this
# corpus can answer keep their best match under ~0.40; queries the corpus is
# silent on (e.g. "does my plan cover acupuncture?", never mentioned anywhere)
# sit at ~0.50+. 0.45 sits in the gap between those two clusters — see
# docs/retrieval-ablation.md (make retrieval-ablation) for the measured
# pass-rate/precision curve. Hand-tuned for this small, fixed corpus; would
# need re-tuning if the corpus grows or changes topic mix.
_MAX_RELEVANT_DISTANCE = 0.45


def _mentioned_plan(query: str) -> str | None:
    """Return the single plan tier named in the query, or None if zero or several are named."""
    lowered = query.lower()
    mentioned = [name for name in _PLAN_TIER_NAMES if name in lowered]
    return mentioned[0] if len(mentioned) == 1 else None


def _plan_scoped_source(source: str, plan: str) -> bool:
    """True if a chunk's source is either plan-agnostic or belongs to the named plan tier."""
    stem = source.lower().removesuffix(".md")
    return stem not in _PLAN_TIER_NAMES or stem == plan


# Filters generic filler from *user query* terms for lexical-overlap
# retrieval scoring. Deliberately kept separate from sut.agent._STOPWORDS,
# which filters *answer* text for citation matching — different domain
# (short queries vs. answer prose), so tuning one should not silently
# change the other.
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
# Hand-tuned starting point; higher values favor literal keyword overlap over
# embedding similarity when re-ranking candidates. See
# docs/retrieval-ablation.md (make retrieval-ablation) for the measured
# pass-rate/precision curve across candidate values.
_LEXICAL_WEIGHT = 0.5


def _chunk_corpus_files(
    md_files: list[Path], chunk_size: int, chunk_overlap: int
) -> tuple[list[str], list[str], list[dict[str, str]]]:
    """Chunk a set of corpus markdown files into (ids, documents, metadatas).

    Shared by PolicyRetriever and InMemoryCosineRetriever's index_corpus —
    both embed the same chunks, just into different storage/search backends.
    """
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
            sub_chunks = _chunk_text(titled_text, chunk_size, chunk_overlap)
            for chunk_text in sub_chunks:
                chunk_id = _stable_id(md_file.name, chunk_text)
                section = heading or _extract_section_heading(chunk_text)
                ids.append(chunk_id)
                documents.append(chunk_text)
                metadatas.append({"source": md_file.name, "section": section})

    return ids, documents, metadatas


def _rerank_and_package(
    query: str,
    docs: list[str],
    metas: list[dict[str, str]],
    distances: list[float],
    fingerprint: str,
    k: int,
) -> list[Chunk]:
    """Re-rank candidates and package the top-k into Chunks.

    Shared by PolicyRetriever and InMemoryCosineRetriever's retrieve() —
    re-ranks embedding distance with a lexical-overlap bonus, applies
    plan-tier query scoping and a distance-margin cutoff, then packages the
    surviving candidates as Chunks. See PolicyRetriever.retrieve's docstring
    for why each step exists.
    """
    candidates = [
        (doc, meta, float(dist) - _LEXICAL_WEIGHT * _keyword_overlap_bonus(query, doc))
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
        if best > _MAX_RELEVANT_DISTANCE:
            # Even the closest match is too far to be relevant — the corpus
            # has nothing on this topic. Return no chunks rather than the
            # least-bad irrelevant ones.
            candidates = []
        else:
            candidates = [c for c in candidates if c[2] <= best + _DISTANCE_MARGIN]

    return [
        Chunk(
            text=doc,
            source=meta.get("source", ""),
            section=meta.get("section", ""),
            chunk_id=_stable_id(meta.get("source", ""), doc),
            rank=rank,
            score=dist,
            corpus_fingerprint=fingerprint,
        )
        for rank, (doc, meta, dist) in enumerate(candidates[:k], start=1)
    ]


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


class Retriever(Protocol):
    """Structural interface shared by PolicyRetriever and FixtureRetriever.

    Lets callers (e.g. CoverageAgent) type against "a retriever" without
    committing to a base class, since the two implementations have
    intentionally different constructors and internals.
    """

    def index_corpus(self, force: bool = False) -> int: ...

    def retrieve(self, query: str, top_k: int | None = None) -> list[Chunk]: ...


class PolicyRetriever:
    """Persist local MiniLM embeddings and retrieve by cosine similarity.

    SQLite is only a local cache for this fixed, small evaluation corpus; it
    does not expose a network service. Its single transaction replaces stale
    corpus/index records atomically. Embedding and ranking behavior is shared
    with :class:`InMemoryCosineRetriever`.
    """

    _SCHEMA_VERSION = "1"

    def __init__(
        self,
        config: RetrievalConfig | None = None,
        embedding_fn: Any = None,
    ) -> None:
        self._config = config or RetrievalConfig()
        self._embedding_fn: Any = embedding_fn or LocalOnnxEmbeddingFunction()
        self._index_path = Path(self._config.persist_dir) / "policy-index.sqlite3"
        self._ids: list[str] = []
        self._documents: list[str] = []
        self._metadatas: list[dict[str, str]] = []
        self._embeddings: np.ndarray[Any, Any] | None = None
        self._fingerprint = ""
        self._embedder_id = _embedding_identity(self._embedding_fn)

    def corpus_fingerprint(self) -> str:
        """Fingerprint of the loaded index (empty until an index is loaded or built)."""
        return self._fingerprint

    def _load_cached_index(self, fingerprint: str) -> bool:
        if not self._index_path.is_file():
            return False
        try:
            with sqlite3.connect(f"file:{self._index_path}?mode=ro", uri=True) as db:
                metadata = dict(db.execute("SELECT key, value FROM metadata"))
                if (
                    metadata.get("schema_version") != self._SCHEMA_VERSION
                    or metadata.get("corpus_fingerprint") != fingerprint
                    or metadata.get("embedding_model") != self._embedder_id
                ):
                    return False
                rows = db.execute(
                    "SELECT chunk_id, document, chunk_metadata, embedding, dimension "
                    "FROM chunks ORDER BY ordinal"
                ).fetchall()
            ids: list[str] = []
            documents: list[str] = []
            metadatas: list[dict[str, str]] = []
            embeddings: list[np.ndarray[Any, Any]] = []
            for chunk_id, document, raw_metadata, raw_embedding, dimension in rows:
                vector = np.frombuffer(raw_embedding, dtype=np.float64)
                if vector.size != dimension or not isinstance(json.loads(raw_metadata), dict):
                    return False
                ids.append(str(chunk_id))
                documents.append(str(document))
                metadatas.append(json.loads(raw_metadata))
                embeddings.append(vector.copy())
            self._ids = ids
            self._documents = documents
            self._metadatas = metadatas
            self._embeddings = (
                np.stack(embeddings) if embeddings else np.zeros((0, 0), dtype=np.float64)
            )
            self._fingerprint = fingerprint
            return True
        except (sqlite3.DatabaseError, OSError, TypeError, ValueError, json.JSONDecodeError):
            # A corrupt disposable cache must be rebuilt from source documents.
            for suffix in ("", "-journal", "-wal", "-shm"):
                try:
                    Path(f"{self._index_path}{suffix}").unlink(missing_ok=True)
                except OSError:
                    return False
            return False

    def _save_index(self) -> None:
        if self._embeddings is None:
            raise RuntimeError("Cannot persist an unbuilt retrieval index.")
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._index_path) as db:
            db.execute("PRAGMA synchronous = FULL")
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS chunks ("
                "ordinal INTEGER NOT NULL UNIQUE, chunk_id TEXT PRIMARY KEY, "
                "document TEXT NOT NULL, chunk_metadata TEXT NOT NULL, "
                "embedding BLOB NOT NULL, dimension INTEGER NOT NULL)"
            )
            db.execute("DELETE FROM chunks")
            db.execute("DELETE FROM metadata")
            db.executemany(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        ordinal,
                        chunk_id,
                        document,
                        json.dumps(metadata, sort_keys=True, separators=(",", ":")),
                        vector.tobytes(),
                        vector.size,
                    )
                    for ordinal, (chunk_id, document, metadata, vector) in enumerate(
                        zip(
                            self._ids,
                            self._documents,
                            self._metadatas,
                            self._embeddings,
                            strict=True,
                        )
                    )
                ],
            )
            db.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                [
                    ("schema_version", self._SCHEMA_VERSION),
                    ("corpus_fingerprint", self._fingerprint),
                    ("embedding_model", self._embedder_id),
                ],
            )
            db.commit()

    def index_corpus(self, force: bool = False) -> int:
        """Load a current persisted index or embed and atomically replace it."""
        corpus_dir = self._config.corpus_dir
        if not corpus_dir.is_dir():
            raise FileNotFoundError(f"Corpus directory not found: {corpus_dir}")
        md_files = sorted(corpus_dir.glob("*.md"))
        if not md_files:
            raise FileNotFoundError(f"No markdown files found in {corpus_dir}")
        current_fingerprint = _corpus_fingerprint(corpus_dir)
        if not force and self._fingerprint == current_fingerprint and self._embeddings is not None:
            return 0
        if not force and self._load_cached_index(current_fingerprint):
            return 0
        ids, documents, metadatas = _chunk_corpus_files(
            md_files, self._config.chunk_size, self._config.chunk_overlap
        )
        if documents:
            embeddings = np.asarray(self._embedding_fn(documents), dtype=np.float64)
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            normalized_embeddings = embeddings / norms
        else:
            normalized_embeddings = np.zeros((0, 0), dtype=np.float64)
        self._ids = ids
        self._documents = documents
        self._metadatas = metadatas
        self._embeddings = normalized_embeddings
        self._fingerprint = current_fingerprint
        self._save_index()
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
        if self._embeddings is None:
            self.index_corpus()
        if self._embeddings is None or not self._ids:
            return []
        query_vec = np.asarray(self._embedding_fn([query]), dtype=np.float64)[0]
        query_norm = np.linalg.norm(query_vec)
        if query_norm > 0:
            query_vec = query_vec / query_norm
        distances = [float(value) for value in 1.0 - self._embeddings @ query_vec]
        return _rerank_and_package(
            query, self._documents, self._metadatas, distances, self.corpus_fingerprint(), k
        )


# ---------------------------------------------------------------------------
# In-memory cosine retriever — same embeddings, no Chroma index
# ---------------------------------------------------------------------------


class InMemoryCosineRetriever:
    """Embeds the corpus with the same ONNX embedding function as PolicyRetriever
    by default, but stores vectors in a plain numpy array and ranks by
    brute-force cosine similarity instead of a persistent SQLite index.

    Demonstrates that the Retriever protocol is satisfied by more than one
    storage/search mechanism — same embedding source by
    default, same chunking and re-ranking logic (both reused from
    module-level helpers), a different retrieval backend underneath.
    Brute-force search is fine at this corpus's scale; it would not be the
    right choice for a larger index. embedding_fn is injectable (see
    PolicyRetriever's docstring).
    """

    def __init__(
        self,
        config: RetrievalConfig | None = None,
        embedding_fn: Any = None,
    ) -> None:
        self._config = config or RetrievalConfig()
        self._embedding_fn: Any = embedding_fn or LocalOnnxEmbeddingFunction()
        self._ids: list[str] = []
        self._documents: list[str] = []
        self._metadatas: list[dict[str, str]] = []
        self._embeddings: Any = None  # numpy array, shape (n_chunks, dim); set on index
        self._fingerprint: str = ""

    def index_corpus(self, force: bool = False) -> int:
        """Chunk and embed all markdown files in corpus_dir. Returns chunks added."""
        corpus_dir = self._config.corpus_dir

        if not corpus_dir.is_dir():
            raise FileNotFoundError(f"Corpus directory not found: {corpus_dir}")

        md_files = sorted(corpus_dir.glob("*.md"))
        if not md_files:
            raise FileNotFoundError(f"No markdown files found in {corpus_dir}")

        current_fingerprint = _corpus_fingerprint(corpus_dir)
        stale = current_fingerprint != self._fingerprint

        if not force and not stale and self._embeddings is not None:
            return 0  # already indexed and up to date

        ids, documents, metadatas = _chunk_corpus_files(
            md_files, self._config.chunk_size, self._config.chunk_overlap
        )

        if ids:
            embeddings = np.asarray(self._embedding_fn(documents), dtype=np.float64)
        else:
            embeddings = np.zeros((0, 0))
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0

        self._ids = ids
        self._documents = documents
        self._metadatas = metadatas
        self._embeddings = embeddings / norms
        self._fingerprint = current_fingerprint

        return len(ids)

    def corpus_fingerprint(self) -> str:
        """Fingerprint of the corpus as currently indexed (empty if never indexed)."""
        return self._fingerprint

    def retrieve(self, query: str, top_k: int | None = None) -> list[Chunk]:
        """Return the top-k most relevant chunks for the given query.

        Mirrors PolicyRetriever.retrieve's re-ranking: plan-tier query
        matching, a lexical-overlap bonus on top of cosine distance, and a
        distance-margin cutoff — see that method's docstring for why each
        step exists.
        """
        k = top_k if top_k is not None else self._config.top_k

        if self._embeddings is None or len(self._ids) == 0:
            self.index_corpus()

        if not self._ids:
            return []

        query_vec = np.asarray(self._embedding_fn([query]), dtype=np.float64)[0]
        query_norm = np.linalg.norm(query_vec)
        if query_norm > 0:
            query_vec = query_vec / query_norm

        similarities = self._embeddings @ query_vec
        distances = [float(d) for d in (1.0 - similarities)]

        return _rerank_and_package(
            query, self._documents, self._metadatas, distances, self.corpus_fingerprint(), k
        )


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
                rank=rank,
            )
            for rank, item in enumerate(raw, start=1)
        ]
