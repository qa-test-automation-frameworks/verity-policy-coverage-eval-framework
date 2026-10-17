# Pinned by digest for reproducible/auditable builds; refresh both the tag
# and digest together (e.g. via Dependabot/Renovate) rather than editing the
# digest alone.
FROM python:3.13.16-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS build

WORKDIR /app
ENV HOME=/app/home

# Distroless Python uses /usr/bin/python. Keep the virtualenv links portable to
# the runtime stage by giving the matching build interpreter that same path.
RUN ln -sf /usr/local/bin/python /usr/bin/python
ENV UV_PYTHON=/usr/bin/python

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 /uv /usr/local/bin/uv

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock .python-version ./
COPY README.md LICENSE ./

# Install all extras (no API key required for Tier-1 checks)
RUN uv sync --frozen --all-extras --no-install-project

# Pre-download the Chroma ONNX embedding model (all-MiniLM-L6-v2) into this
# layer so `docker run` doesn't need network access. Same cache path CI's
# actions/cache step keys on (~/.cache/chroma/onnx_models). Placed before
# COPY src/ so it stays cached across source-only changes.
RUN mkdir -p "$HOME" && uv run --no-sync python -c \
    "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(['warmup'])"

# Copy source
COPY src/ ./src/
COPY tests/ ./tests/
COPY datasets/ ./datasets/
COPY promptfoo/ ./promptfoo/
COPY scripts/ ./scripts/
COPY docs/ ./docs/
COPY reports/semantic/results.json ./reports/semantic/results.json
COPY Makefile ./

# Install the project itself
RUN uv sync --frozen --all-extras

# The final image needs the installed virtualenv, not uv's duplicate package
# archives. Keep the separately pre-downloaded Chroma embedding model cache.
RUN uv cache clean

FROM gcr.io/distroless/python3-debian13:nonroot@sha256:83aa8d4f74a4d7f7cf2d472054139bef71a927b76c680c0f2e1021d6b1d6d732 AS runtime

WORKDIR /app
ENV HOME=/app/home
ENV PYTHONPATH=/app/src

COPY --from=build /app/.venv/ /app/.venv/
COPY --from=build --chown=65532:65532 /app/home/.cache/chroma/onnx_models/ /app/home/.cache/chroma/onnx_models/
COPY --from=build /app/pyproject.toml ./pyproject.toml
COPY --from=build /app/src/ ./src/
COPY --from=build /app/tests/ ./tests/
COPY --from=build /app/datasets/ ./datasets/
COPY --from=build /app/promptfoo/ ./promptfoo/
COPY --from=build /app/scripts/ ./scripts/
COPY --from=build /app/docs/ ./docs/
COPY --from=build --chown=65532:65532 /app/reports/semantic/results.json ./reports/semantic/results.json
COPY --from=build /app/Makefile ./Makefile

# Default: run Tier-1 checks (no live calls, no API key)
ENTRYPOINT ["/app/.venv/bin/python"]
CMD ["-m", "pytest", "-p", "no:cacheprovider", "-m", "not live", "--tb=short", "-q"]
