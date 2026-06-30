# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

## [Unreleased]

### Added — M0 (Foundation)
- Repo scaffold: src layout, pyproject.toml, uv, ruff, mypy strict, pre-commit
- `verity.config`: Pydantic-settings config for provider, judge, retrieval
- `verity.providers`: LiteLLM wrapper routing to Z.ai / OpenRouter / Together
- `verity.cost`: token/cost accounting with per-run accumulator
- CI skeleton: `pr-gate.yml` (Tier 1 — lint, type, unit; no live calls)
- Makefile with task entrypoints; `.env.example`

### Added — M2 (Deterministic Tier)
- `verity.golden`: typed `GoldenCase` Pydantic schema with `expects_defect` flag; `load_golden()` loader
- `datasets/golden/cases.yaml`: 15 versioned cases — 7 clean controls + 8 defect cases (one per seeded defect)
- `verity.cassettes`: SHA-256 keyed cassette library (`CassetteLibrary`, `request_key`, `CassetteMissError`)
- `verity.config`: `cassette_mode` / `cassette_dir` settings for record/replay/off
- `verity.providers`: cassette record/replay integration in `LLMProvider.complete()`
- `sut.retriever.FixtureRetriever`: drop-in retriever serving pre-authored `Chunk` lists from JSON files; no Chroma/ONNX needed for Tier-1
- `datasets/cassettes/retrieval/`: 15 hand-curated retrieval fixture JSON files (one per golden case)
- `verity.checks`: `validate_response_schema`, `check_refusal`, `check_tool_args`, `scan_pii`, `check_pii`, `scan_injection`, `check_injection`, `check_must_contain`, `check_must_not_contain`
- `scripts/record_cassettes.py`: authored (no API key) and live cassette generation; `make record` target
- `datasets/cassettes/authored/`: 14 hand-authored response YAML files (control + defect turns)
- 14 committed hash-keyed cassette JSON files for hermetic Tier-1 replay
- `tests/deterministic/`: 97-test suite — schema, refusal, tool-args, PII, injection, regression, defect detection
- **Defects #5–#8 caught deterministically** — zero live calls; <1 s total run time

### Added — M1 (SUT — Policy Coverage Copilot)
- Fictional corpus: `bronze.md`, `silver.md`, `gold.md`, `definitions.md`, `exclusions.md`, `amendments.md`
- All 8 seeded defects baked into corpus and SUT code
- `sut.tools.coverage_calculator`: deterministic Pydantic-typed cost calculator + tool schema
- `sut.retriever`: Chroma + built-in ONNX embeddings, markdown-aware chunker
- `sut.guardrails`: input scope check + output PII scrubber (with intentional seeded gaps)
- `sut.agent`: full agent loop with tool-use, citations, structured `AgentResponse`
- Unit tests: coverage calculator, guardrails, retriever chunker, config, cost, providers (mocked)
- `docs/seeded-defects.md`: living catalog of all 8 seeded defects
