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

### Added — M1 (SUT — Policy Coverage Copilot)
- Fictional corpus: `bronze.md`, `silver.md`, `gold.md`, `definitions.md`, `exclusions.md`, `amendments.md`
- All 8 seeded defects baked into corpus and SUT code
- `sut.tools.coverage_calculator`: deterministic Pydantic-typed cost calculator + tool schema
- `sut.retriever`: Chroma + built-in ONNX embeddings, markdown-aware chunker
- `sut.guardrails`: input scope check + output PII scrubber (with intentional seeded gaps)
- `sut.agent`: full agent loop with tool-use, citations, structured `AgentResponse`
- Unit tests: coverage calculator, guardrails, retriever chunker, config, cost, providers (mocked)
- `docs/seeded-defects.md`: living catalog of all 8 seeded defects
