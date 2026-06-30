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
make test-deterministic  # Tier-1 deterministic eval (cassette replay; no API key)
make record            # regenerate cassettes from authored YAML fixtures
make smoke             # one live provider call (requires API key in .env)
make demo QUERY="What is my Silver plan deductible?"
```

### Reports & Pages

```bash
make defects-report    # regenerate docs/defects-caught.md (hermetic, no API key)
make report-allure     # run hermetic suites with --alluredir; generate Allure HTML
make report-site       # defects-report + build static site/ with all report pages
make calibrate         # hermetic judge calibration replay (no API key)
make calibrate-live    # live judge calibration recording (requires API key)
make redteam           # hermetic adversarial suite (no API key)
make trace-demo        # one-shot OTel trace demo writing spans to reports/traces/
```

The static site is published to GitHub Pages via `.github/workflows/pages.yml` after Pages is enabled for the repository. Pages include the defects-caught matrix, calibration report, cost summary, and Allure test results.

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

### Live-tier flake policy

Tier 1 should be deterministic and must not use retries to hide failures. For live Tier 2/Tier 3 tests, mark known provider-instability cases with `@pytest.mark.flaky` only after recording the failure mode in the test or linked issue. Use `@pytest.mark.quarantine` for tests that should keep running for signal but should not block merges until the owner removes the marker.

### Troubleshooting

- First `PolicyRetriever` use may download the local ONNX embedding model through Chroma; retry after the cache is populated if the network is interrupted.
- Run commands through `make` or set `PYTHONPATH=src` manually when invoking modules directly.
- Missing provider-key warnings are expected for Tier 1; live calls require `VERITY_ZAI_API_KEY`, `VERITY_OPENROUTER_API_KEY`, or `VERITY_TOGETHER_API_KEY`.
- Treat `.env.example` provider endpoints as templates and verify the model slug/base URL with your provider before live runs.

### CI

- **Tier 1 (PR gate):** runs on every push; lint + type + unit + deterministic tests; no live calls; must pass.
- **Tier 2 (Semantic eval):** runs on merge to main; requires `ZAI_API_KEY` GitHub Secret.
- **Tier 3 (Adversarial):** weekly scheduled; non-blocking but reports published.

### Cassette workflow

Tier-1 (`tests/deterministic/`) runs against pre-recorded cassette JSON files so no API key is needed in CI. The cassettes are authored by hand and stored in `datasets/cassettes/`.

**To add a new golden case:**

1. Add the case to `datasets/golden/cases.yaml` with `id`, `query`, `member_id`, behavior, etc.
2. Add a retrieval fixture: `datasets/cassettes/retrieval/<case_id>.json` — a JSON array of `{text, source, section, chunk_id}` objects matching the corpus chunks the agent should "see" for this query.
3. If `expects_defect: false` (clean control), author a correct response in `datasets/cassettes/authored/<case_id>.yaml`:
   ```yaml
   turns:
     - content: "The Silver plan covers specialist visits at a $60 copay."
       prompt_tokens: 120
       completion_tokens: 35
   ```
   If the response includes a tool call, add a second turn; see existing authored YAMLs for examples.
4. Run `make record` to compute the SHA-256 request key and write the cassette JSON file.
5. Commit the new retrieval fixture, authored YAML, and generated cassette JSON alongside your golden case and new tests.

**To update an existing cassette** (e.g., after changing the system prompt or retrieval fixtures):

```bash
make record CASE=<case_id>     # regenerate only one case
# or
make record                    # regenerate all
git add datasets/cassettes/ && git commit -m "chore(cassettes): update cassettes for <reason>"
```

Note: changing any input to the agent (model, temperature, system prompt template, corpus chunks, or tool schema) changes the request hash and invalidates all downstream cassettes. The manifest test in `test_regression_cassette.py` will fail, telling you exactly which cases need to be re-recorded.
