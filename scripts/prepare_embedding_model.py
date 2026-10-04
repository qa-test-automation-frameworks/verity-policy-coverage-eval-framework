"""Provision the real default embedding model before parallel test workers start.

This preparation may download Chroma's public ONNX asset. Chroma performs its
native checksum verification; test execution still uses the actual model.
It does not require a provider key or evaluate an LLM.
"""

from __future__ import annotations

import json

from chromadb.utils.embedding_functions import DefaultEmbeddingFunction


def main() -> None:
    """Initialize and validate one real embedding before xdist can share its cache."""
    vectors = DefaultEmbeddingFunction()(["Embedding model readiness control"])
    if len(vectors) != 1 or len(vectors[0]) == 0:
        raise RuntimeError("Default embedding model returned an invalid readiness result")
    print(json.dumps({"model": "Chroma default ONNX", "dimensions": len(vectors[0])}))


if __name__ == "__main__":
    main()
