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
# Edit .env — add your VERITY_ZAI_API_KEY (or VERITY_OPENROUTER_API_KEY / VERITY_TOGETHER_API_KEY)
```

All env vars use the canonical `VERITY_*` prefix (see `.env.example`); bare
names like `ZAI_API_KEY` are accepted as legacy aliases but `VERITY_*` is
what CI and the docs above use.

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

Tier 1 tests run serially by default. For a faster local loop, run them in
parallel with `pytest-xdist` (installed via the `dev` extra):

```bash
uv run pytest -m "not live" -n auto
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
VERITY_OPENROUTER_API_KEY=your-key-here
```

### Code style

- **ruff** (lint + format) — configured in `pyproject.toml`
- **mypy strict** — zero untyped functions; all ignores must be justified inline
- No unnecessary comments; no docstrings beyond one-line function summaries
- Tests: pytest; unit tests in `tests/unit/`; no mocking of internal logic

### Live-tier flake policy

Tier 1 should be deterministic and must not use retries to hide failures. For live Tier 2/Tier 3 tests, mark known provider-instability cases with `@pytest.mark.flaky` only after recording the failure mode in the test or linked issue. Use `@pytest.mark.quarantine` for tests that should keep running for signal but should not block merges until the owner removes the marker.

Before applying either marker, get evidence rather than guessing: `make flake-check ARGS='--runs 5 -- tests/semantic -m live'` runs the given pytest selection N times and reports which tests actually flipped between pass and fail across runs (`scripts/detect_flaky_tests.py`). It writes `reports/flake/flake-report.json` and never fails the command unless `--strict` is passed — it's diagnostic input for the marker decision, not a new gate.

### Troubleshooting

- First `PolicyRetriever` use may download the local ONNX embedding model through Chroma; retry after the cache is populated if the network is interrupted.
- Run commands through `make` or set `PYTHONPATH=src` manually when invoking modules directly.
- Missing provider-key warnings are expected for Tier 1; live calls require `VERITY_ZAI_API_KEY`, `VERITY_OPENROUTER_API_KEY`, or `VERITY_TOGETHER_API_KEY`.
- Treat `.env.example` provider endpoints as templates and verify the model slug/base URL with your provider before live runs.

### CI

- **Tier 1 (PR gate):** runs on every push; lint + type + unit + deterministic tests; no live calls; must pass.
- **Tier 2 (Semantic eval):** runs on merge to main; requires the `VERITY_*_API_KEY` GitHub Secret matching `VERITY_PROVIDER` (e.g. `VERITY_ZAI_API_KEY`).
- **Tier 3 (Adversarial):** weekly scheduled; non-blocking but reports published.

Only Tier 1 (`pr-gate.yml`'s `lint-type-test` job, run as a Python 3.12 + 3.13 matrix) is
intended to gate merges — set both matrix checks as required status checks under the
repository's branch protection rules for `main`. Tier 2/3 are informational and should
not block a PR even if their optional secrets are unset.

See [`docs/ci-policy.md`](docs/ci-policy.md) for the full list of required checks, what each
one enforces, and this project's release criteria.

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

### Mutation testing

`src/sut/tools/coverage_calculator.py` (the pricing arithmetic) and
`src/verity/checks.py` (the core response checks) have a mutation-testing gate via
[mutmut](https://mutmut.readthedocs.io/), scoped to those two modules because they are pure,
have no I/O, and are where a 100% line-coverage number is least trustworthy on its own (line
coverage proves a line ran, not that its output was checked). Mutation testing proves the
latter.

```bash
uv sync --extra mutation
make mutation-test    # strict — fails the command on surviving mutants
make mutation-report  # diagnostic — always prints results, never fails the command
```

This is a local/dev quality check, not part of the required CI gate (mutation testing is
too slow to run on every PR) — see [`docs/ci-policy.md`](docs/ci-policy.md) for what actually
gates merges.

### Pre-publish checklist

Before making this repository public or sharing it externally, work through this list:

- **Rotate any real provider keys used during local development.** A local `.env` is
  gitignored and never committed, but keys typed into it during development (Z.ai,
  OpenRouter, Together, etc.) should still be rotated or revoked before the repo is
  broadcast publicly — treat any key that ever touched a local `.env` as exposed to
  whoever had access to that machine.
- **Verify no secret-shaped strings are in tracked files.** `git grep` for provider key
  prefixes (`sk-`, `nvapi-`, etc.) across the full history, not just the working tree —
  the gitleaks pre-commit hook covers new commits but not history predating it.
- **Confirm a known-working live provider route.** `.env.example`'s default model slug and
  base URL are templates, not guarantees. Run `scripts/select_openrouter_free_models.py` (or
  the equivalent for your provider) to confirm a specific model slug and base URL currently
  work, and note the exact slug and the date it was verified in `.env.example` or the README
  so a first-time contributor's `make smoke` doesn't fail on a stale default.
- **Double-check recordings/screenshots/logs** made during development don't echo a real key
  in a terminal prompt, environment dump, or trace file before including them in any
  write-up.
