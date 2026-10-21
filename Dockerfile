# Pinned by digest for reproducible/auditable builds; refresh both the tag
# and digest together (e.g. via Dependabot/Renovate) rather than editing the
# digest alone.
FROM python:3.13.16-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS build

WORKDIR /app
ENV HOME=/app/home
ENV FASTEMBED_CACHE_PATH=/app/home/.cache/fastembed

# Distroless Python uses /usr/bin/python. Keep the virtualenv links portable to
# the runtime stage by giving the matching build interpreter that same path.
RUN ln -sf /usr/local/bin/python /usr/bin/python
ENV UV_PYTHON=/usr/bin/python

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 /uv /usr/local/bin/uv

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock .python-version ./
COPY README.md LICENSE ./

# Install the development/test extra only. CI-only security auditing lives in
# its own extra and is not needed in this image. The Tier-1 image also excludes
# the optional semantic extra (RAGAS/DeepEval), which runs separately in CI.
RUN uv sync --frozen --extra dev --no-install-project

# Pre-download the FastEmbed ONNX embedding model (all-MiniLM-L6-v2) into this
# layer so `docker run` doesn't need network access. Same cache path CI's
# actions/cache step keys on (~/.cache/fastembed). Placed before
# COPY src/ so it stays cached across source-only changes.
RUN mkdir -p "$FASTEMBED_CACHE_PATH" && uv run --no-sync python -c \
    "from fastembed import TextEmbedding; list(TextEmbedding(model_name='sentence-transformers/all-MiniLM-L6-v2').embed(['warmup']))"

# Copy source
COPY src/ ./src/
COPY tests/ ./tests/
COPY datasets/ ./datasets/
COPY promptfoo/ ./promptfoo/
COPY scripts/ ./scripts/
COPY portfolio/evidence/ ./portfolio/evidence/
COPY .pip-audit-ignore .trivyignore ./
COPY docs/ ./docs/
COPY reports/semantic/results.json ./reports/semantic/results.json
COPY Makefile ./

# Install the project itself into a fresh environment after all source and
# dependency inputs are present. The metadata gate scans recursively so it also
# catches stale or duplicate package records nested below site-packages.
RUN rm -rf .venv && uv sync --frozen --extra dev && \
    uv run python scripts/check_runtime_package_versions.py

# The final image needs the installed virtualenv, not uv's duplicate package
# archives. Keep the separately pre-downloaded FastEmbed model cache.
RUN uv cache clean && rm -rf /usr/local/lib/python3.13/site-packages

# The minimal runtime base omits libffi, SQLite, and bzip2, which Python's stdlib
# extensions need. Copy the same-architecture runtime libraries from the build.
RUN set -eux; \
    mkdir -p /opt/runtime-libs; \
    for pattern in libffi.so.8 libsqlite3.so.0 libbz2.so.1.0 liblzma.so.5; do \
        for lib in /usr/lib/*-linux-gnu/${pattern}*; do \
            destination="/opt/runtime-libs/${lib#/usr/lib/}"; \
            mkdir -p "$(dirname "${destination}")"; \
            cp -a "${lib}" "${destination}"; \
        done; \
    done

FROM gcr.io/distroless/cc-debian13:nonroot@sha256:e792ab3d241a468a4fd7519ddbbebe66b49b5f365771716ea688ad40b6c6f1c2 AS runtime

WORKDIR /app
ENV HOME=/app/home
ENV FASTEMBED_CACHE_PATH=/app/home/.cache/fastembed
ENV PYTHONPATH=/app/src
ENV LD_LIBRARY_PATH=/usr/local/lib:/opt/runtime-libs/x86_64-linux-gnu:/opt/runtime-libs/aarch64-linux-gnu

COPY --from=build /usr/bin/python /usr/bin/python
COPY --from=build /usr/local/bin/python* /usr/local/bin/
COPY --from=build /usr/local/lib/libpython3.13.so* /usr/local/lib/
COPY --from=build /usr/local/lib/python3.13/ /usr/local/lib/python3.13/
COPY --from=build /opt/runtime-libs/ /opt/runtime-libs/
COPY --from=build /app/.venv/ /app/.venv/
COPY --from=build --chown=65532:65532 /app/home/.cache/fastembed/ /app/home/.cache/fastembed/
COPY --from=build /app/pyproject.toml ./pyproject.toml
COPY --from=build /app/uv.lock ./uv.lock
COPY --from=build /app/README.md ./README.md
COPY --from=build /app/LICENSE ./LICENSE
COPY --from=build /app/src/ ./src/
COPY --from=build /app/tests/ ./tests/
COPY --from=build /app/datasets/ ./datasets/
COPY --from=build /app/promptfoo/ ./promptfoo/
COPY --from=build /app/scripts/ ./scripts/
COPY --from=build /app/portfolio/evidence/ ./portfolio/evidence/
COPY --from=build /app/.pip-audit-ignore ./.pip-audit-ignore
COPY --from=build /app/.trivyignore ./.trivyignore
COPY --from=build /app/docs/ ./docs/
COPY --from=build --chown=65532:65532 /app/reports/semantic/results.json ./reports/semantic/results.json
COPY --from=build /app/Makefile ./Makefile

# Default: run Tier-1 checks through the same no-key, offline-after-preparation
# launcher used by local Make targets and CI.
ENTRYPOINT ["/app/.venv/bin/python", "/app/scripts/run_hermetic.py", "--", "/app/.venv/bin/python"]
CMD ["-m", "pytest", "-p", "no:cacheprovider", "-m", "not live and not semantic", "--tb=short", "-q"]
