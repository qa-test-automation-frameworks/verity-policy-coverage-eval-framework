# Pinned by digest for reproducible/auditable builds; refresh both the tag
# and digest together (e.g. via Dependabot/Renovate) rather than editing the
# digest alone.
FROM python:3.13.16-slim@sha256:3dd7cc108ec1493442514f5c2a871af6af0ec31d768ff6e378a93340c3b3db5f

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.11.25@sha256:1e3808aa9023d0980e7c15b1fa7c1ac16ff35925780cf5c459858b2d693f01a9 /uv /usr/local/bin/uv

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock .python-version ./
COPY README.md LICENSE ./

# Install all extras (no API key required for Tier-1 checks)
RUN uv sync --frozen --all-extras --no-install-project

# Pre-download the Chroma ONNX embedding model (all-MiniLM-L6-v2) into this
# layer so `docker run` doesn't need network access. Same cache path CI's
# actions/cache step keys on (~/.cache/chroma/onnx_models). Placed before
# COPY src/ so it stays cached across source-only changes.
RUN uv run --no-sync python -c \
    "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(['warmup'])"

# Copy source
COPY src/ ./src/
COPY tests/ ./tests/
COPY datasets/ ./datasets/
COPY scripts/ ./scripts/
COPY docs/ ./docs/
COPY Makefile ./

# Install the project itself
RUN uv sync --frozen --all-extras

RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app/src

# Default: run Tier-1 checks (no live calls, no API key)
CMD ["uv", "run", "pytest", "-m", "not live", "--tb=short", "-q"]
