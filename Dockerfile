# Pinned by digest for reproducible/auditable builds; refresh both the tag
# and digest together (e.g. via Dependabot/Renovate) rather than editing the
# digest alone.
FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest@sha256:3d868e555f8f1dbc324afa005066cd11e1053fc4743b9808ca8025283e65efa5 /uv /usr/local/bin/uv

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
COPY README.md LICENSE ./
COPY Makefile ./

# Install the project itself
RUN uv sync --all-extras

RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app/src

# Default: run Tier-1 checks (no live calls, no API key)
CMD ["uv", "run", "pytest", "-m", "not live", "--tb=short", "-q"]
