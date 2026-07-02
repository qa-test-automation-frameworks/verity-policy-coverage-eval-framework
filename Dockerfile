FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock ./

# Install all extras (no API key required for Tier-1 checks)
RUN uv sync --all-extras --no-install-project

# Pre-download the Chroma ONNX embedding model (all-MiniLM-L6-v2) into this
# layer so `docker run` doesn't need network access. Same cache path CI's
# actions/cache step keys on (~/.cache/chroma/onnx_models). Placed before
# COPY src/ so it stays cached across source-only changes.
RUN uv run python -c \
    "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(['warmup'])"

# Copy source
COPY src/ ./src/
COPY tests/ ./tests/
COPY datasets/ ./datasets/
COPY scripts/ ./scripts/
COPY docs/ ./docs/
COPY Makefile ./

# Install the project itself
RUN uv sync --all-extras

ENV PYTHONPATH=/app/src

# Default: run Tier-1 checks (no live calls, no API key)
CMD ["uv", "run", "pytest", "-m", "not live", "--tb=short", "-q"]
