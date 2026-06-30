"""RAG retriever: chunk policy corpus → embed → Chroma → retrieve.

Uses Chroma's built-in ONNX embedding function (all-MiniLM-L6-v2) so retrieval
is fully local and reproducible — no external embedding API calls.

The ONNX model is downloaded and cached by Chroma on first use; subsequent runs
are offline. Document this in CONTRIBUTING and cache in CI if needed (M2).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from verity.config import RetrievalConfig


@dataclass(frozen=True)
class Chunk:
    """A retrieved text chunk with provenance metadata."""

    text: str
    source: str       # filename (relative to corpus_dir)
    section: str      # detected heading, or ""
    chunk_id: str     # stable hash of (source, text)


def _extract_section_heading(text: str) -> str:
    """Return the first markdown heading found in the chunk, or empty string."""
    match = re.search(r"^#{1,3}\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


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


def _stable_id(source: str, text: str) -> str:
    return hashlib.sha256(f"{source}||{text}".encode()).hexdigest()[:16]


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
            raw = md_file.read_text(encoding="utf-8")
            chunks = _chunk_text(raw, self._config.chunk_size, self._config.chunk_overlap)
            for chunk_text in chunks:
                chunk_id = _stable_id(md_file.name, chunk_text)
                section = _extract_section_heading(chunk_text)
                ids.append(chunk_id)
                documents.append(chunk_text)
                metadatas.append({"source": md_file.name, "section": section})

        if ids:
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

        return len(ids)

    def retrieve(self, query: str, top_k: int | None = None) -> list[Chunk]:
        """Return the top-k most relevant chunks for the given query."""
        k = top_k if top_k is not None else self._config.top_k
        collection = self._get_collection()

        if collection.count() == 0:
            self.index_corpus()

        results = collection.query(
            query_texts=[query],
            n_results=min(k, collection.count()),
            include=["documents", "metadatas"],
        )

        chunks: list[Chunk] = []
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        for doc, meta in zip(docs, metas, strict=True):
            chunks.append(
                Chunk(
                    text=doc,
                    source=meta.get("source", ""),
                    section=meta.get("section", ""),
                    chunk_id=_stable_id(meta.get("source", ""), doc),
                )
            )
        return chunks
