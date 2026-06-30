# Contributing

## Development Setup

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (install via `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### First-time setup

```bash
git clone <repo-url>
cd verity-policy-coverage-eval-framework
uv sync --all-extras
pre-commit install
cp .env.example .env
# Edit .env — add your ZAI_API_KEY (or OPENROUTER_API_KEY / TOGETHER_API_KEY)
```

### Corpus indexing note

The RAG retriever uses Chroma with the built-in ONNX embedding function
(`all-MiniLM-L6-v2`). On first use, Chroma downloads this model (~90 MB) and
caches it locally. Subsequent runs are fully offline. The `.chroma/` directory
(persisted vector store) is gitignored; it is rebuilt on first `make demo` run
or `retriever.index_corpus()` call.

### Common tasks

```bash
make install           # uv sync
make lint              # ruff lint
make format            # ruff format
make type              # mypy strict
make test              # unit tests (no live calls)
make smoke             # one live GLM-5.2 call (requires API key in .env)
make demo QUERY="What is my Silver plan deductible?"
```

### Running with a different provider

Set `VERITY_PROVIDER` in `.env`:

```bash
VERITY_PROVIDER=openrouter
OPENROUTER_API_KEY=your-key-here
```

### Code style

- **ruff** (lint + format) — configured in `pyproject.toml`
- **mypy strict** — zero untyped functions; all ignores must be justified inline
- No unnecessary comments; no docstrings beyond one-line function summaries
- Tests: pytest; unit tests in `tests/unit/`; no mocking of internal logic

### CI

- **Tier 1 (PR gate):** runs on every push; lint + type + unit tests; no live calls; must pass.
- **Tier 2 (Semantic eval):** runs on merge to main; requires `ZAI_API_KEY` GitHub Secret.
- **Tier 3 (Adversarial):** weekly scheduled; non-blocking but reports published.
