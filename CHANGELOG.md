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

### Added — M5 (Adversarial Tier / Tier 3)
- `verity.adversarial`: `AdversarialProbe` Pydantic schema (id, category, prompt, member_id, defense, expected_outcome, must_not_contain, retrieval_fixture_id); `load_probes(path)` YAML loader
- `datasets/adversarial/probes.yaml`: 14 probes across 5 categories — 3 injection, 3 jailbreak, 3 PII extraction, 3 harmful content, 2 coverage hallucination
- `datasets/cassettes/retrieval/adv-{injection-002,003,pii-002,003,harmful-003}.json`: novel retrieval fixtures for non-golden probes
- `datasets/adversarial/cassettes/`: 14 authored response cassettes; injection-001 and pii-001 reuse golden cassettes to guarantee key consistency
- `tests/adversarial/conftest.py`: `run_probe()` helper wiring `CassetteLibrary` + `FixtureRetriever` + `CoverageAgent` for hermetic replay; `_settings` fixture
- `tests/adversarial/test_redteam_hermetic.py`: parametrized across all 14 probes; `_evaluate_probe()` dispatches by defense type; mandatory assertions `test_injection_defect_7_is_caught` and `test_pii_defect_8_is_caught`; `test_print_vulnerability_summary` prints DEFENDED/BREACHED table — 17 tests, zero API calls
- `scripts/author_adversarial_cassettes.py`: reproduces the full cassette set from probe YAML + retrieval fixtures + system-prompt pipeline
- `promptfoo/provider.py`: custom Python provider wrapping `CoverageAgent`; returns `{output, tokenUsage}` for promptfoo assertion evaluation
- `promptfoo/redteam.yaml`: 13 prompts with not-contains assertions for injection compliance language, PII echoes, and hallucinated coverage claims
- `.github/workflows/adversarial.yml`: weekly + on-demand CI; hermetic pytest always runs; Promptfoo live eval + calibration live run gated on `VERITY_ZAI_API_KEY` secret
- `Makefile`: `make redteam` (hermetic only) and `make redteam-live` (hermetic + Promptfoo)
- `docs/seeded-defects.md`: defects #7 and #8 "Caught by" entries updated with hermetic test references

### Added — M4 (Judge Calibration & Self-Bias)
- `verity.calibration`: `CalibrationCase` Pydantic schema; `load_calibration()`; `AgreementReport` + `SelfBiasReport` frozen dataclasses; `compute_agreement()` (raw %, Cohen's kappa, per-metric MAE); `compute_self_bias()` (delta = E[judge−human | glm] − E[judge−human | other]); `build_scoring_prompt()`, `parse_judge_score()`, `score_case()`, `score_all()` for rubric-based scoring
- `verity.metrics.rubrics`: added `FAITHFULNESS_RUBRIC` (calibration reuses all four Tier-2 rubrics)
- `verity.judges`: `ProviderJudge` now propagates `cassette_mode` + `cassette_dir` into internal judge `Settings`, enabling calibration cassette replay
- `datasets/calibration/labeled.yaml`: 32 human-annotated cases — 8 per metric (completeness, disambiguation, refusal, faithfulness), 16 GLM-family / 16 other-family for self-preference measurement
- `datasets/calibration/cassettes/`: 32 SHA-256-keyed authored judge-score cassettes for hermetic replay with no API key
- `scripts/run_calibration.py`: three-mode runner (author, record-live, replay); markdown report + JSON artifact output
- `docs/calibration-report.md`: committed report — raw agreement 96.9%, Cohen's kappa 0.934, MAE 0.028; self-preference delta +0.056 (GLM outputs scored 0.056 higher than human on average); per-metric breakdown and threshold traceability
- `Makefile`: `make calibrate` (hermetic, no key) and `make calibrate-live` (live recording) targets
- 40 unit tests covering schema validation, loader, agreement/kappa/MAE, self-bias delta, prompt builder, and score parser edge cases

### Added — M3 (Semantic Tier)
- `pyproject.toml`: optional `semantic` dependency group (`deepeval>=1.5.0`, `ragas>=0.2.0`); mypy overrides for third-party typed/untyped packages
- `verity.judges`: `ProviderJudge` wraps `LLMProvider` for plug-and-play judge routing; `DeepEvalJudge` adapter (lazy `DeepEvalBaseLLM` subclass); `RagasJudge` duck-type LangChain shim (avoids `langchain_community` import error)
- `verity.metrics.rubrics`: three G-Eval rubric texts — completeness (#3 multi-hop), disambiguation (#4 contradiction), refusal-boundary (#6 medical advice)
- `verity.metrics.deepeval_metrics`: six metric factory functions with per-metric thresholds; lazy deepeval import (only when metric is constructed); `make_hallucination`, `make_answer_relevancy`, `make_completeness`, `make_disambiguation`, `make_refusal_geval`, `make_tool_correctness`
- `verity.metrics.ragas_metrics`: three RAGAS metric factories with per-metric thresholds — `make_faithfulness`, `make_context_precision`, `make_ragas_answer_relevancy`
- `verity.statistics`: `StatResult` frozen dataclass; `run_n_samples(fn, n)` runs a scoring function N times; `aggregate(scores)` → mean/median/stdev/pass_rate; `threshold_pass(stat, threshold, mode)` — modes: mean, median, pass_rate, all
- `tests/semantic/`: 6-file Tier-2 suite (conftest + faithfulness, completeness, disambiguation, tool-use, refusal, relevancy); all marked `semantic`+`live`; clean cases assert score ≥ threshold; defect cases assert score < threshold (defect detected = green test); auto-skips when no API key is configured
- `.github/workflows/semantic-eval.yml`: triggers on push to main, nightly at 02:00 UTC, and `workflow_dispatch`; no-ops gracefully when no API key secret is set; installs semantic extras, indexes corpus, runs semantic suite
- `docs/thresholds.md`: per-metric threshold table with defect coverage map, statistical method description, and rationale for each threshold value

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
