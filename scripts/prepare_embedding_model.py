"""Provision the real default embedding model before parallel test workers start.

This may download the public FastEmbed ONNX asset. Test execution still uses
the actual model; it does not require a provider key or evaluate an LLM.
"""

from __future__ import annotations

import json

from sut.retriever import LocalOnnxEmbeddingFunction


def main() -> None:
    """Initialize and validate one real embedding before xdist can share its cache."""
    vectors = LocalOnnxEmbeddingFunction()(["Embedding model readiness control"])
    if len(vectors) != 1 or len(vectors[0]) == 0:
        raise RuntimeError("Default embedding model returned an invalid readiness result")
    print(
        json.dumps({"model": LocalOnnxEmbeddingFunction.model_name, "dimensions": len(vectors[0])})
    )


if __name__ == "__main__":
    main()
