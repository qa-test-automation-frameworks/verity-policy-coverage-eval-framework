# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)

## [Unreleased]

## [0.1.0] - 2026-07-02

First tagged release. Includes committed live evidence: a Tier-2 semantic run
and a judge calibration run against `openai/gpt-4o-mini` via OpenRouter (see
README Limitations for why that substitutes for the GLM-4.5 default), 8
paraphrase/typo variants of the seeded defects for phrasing-robustness, a
Python 3.12/3.13 CI matrix, SHA-pinned GitHub Actions, and CI status badges.

### Added
- `datasets/adversarial/probes.yaml`: `adv-crossmember-001` — a cross-member confidentiality probe verifying the agent never fabricates or leaks another member's PII when asked about a member other than the one it was invoked for; wired into the hermetic pytest suite and `promptfoo/redteam.yaml`
- `datasets/golden/cases.yaml`: `ctrl-gold-family-deductible` (family-tier deductible figure, distinct from the individual-only cases already covered) and `ctrl-bronze-oop-cap-tool` (new member MBR-006, deductible fully met and $200 short of the OOP max, exercising `calculate_coverage`'s out-of-pocket-cap branch end-to-end through the agent and tool path rather than only the pure-function unit tests)

### Added — Documentation & Polish
- `docs/architecture.md`: full system overview replacing the stub — two-package monorepo layout, three-tier eval pyramid, component walk-through tables for all `verity/` and `sut/` modules, `agent.answer()` data flow with span points, CI tier/trigger table, ADR summary table, cross-links to all related docs
- `docs/adr/`: 5 Architecture Decision Records (MADR-style with Context/Decision/Consequences/Alternatives):
  - `0001-glm-4-5-model-choice.md` — GLM-4.5 via LiteLLM; cost, OpenAI-compat, multi-provider portability
  - `0002-three-layer-eval-pyramid.md` — solves non-determinism, cost, and provider coupling
  - `0003-cassette-replay-for-ci.md` — SHA-256 keyed VCR-style replay; zero live calls in PR gate
  - `0004-judge-calibration-and-self-bias.md` — kappa=0.934, self-bias delta=+0.056 documented and justified
  - `0005-statistical-thresholds.md` — distribution-over-N replaces brittle single-run assertions
  - `docs/adr/README.md` — index table + MADR template
- `README.md`: Reports table linking all committed docs; quickstart updated with `make defects-report` and Tier-2 cost note; repo structure block expanded with `promptfoo/`, `scripts/`, populated `docs/` and CI workflows; status line updated to M0-M8 complete
- `CONTRIBUTING.md`: Reports & Pages subsection with all new make targets and Pages publishing note

### Added — CI Orchestration & Reporting
- `scripts/defects_report.py`: hermetic defects-caught matrix generator — runs cassette-replay checks for defects 5-8 (deterministic + adversarial), ingests `reports/semantic/results.json` when present to upgrade defects 1-4 from COVERED to VERIFIED; emits committed `docs/defects-caught.md` and git-ignored `reports/defects/defects-caught.json`; `make defects-report`
- `docs/defects-caught.md`: committed hermetic proof matrix (regenerable; always green for a fresh clone)
- `tests/unit/test_defects_report.py`: 19 unit tests covering catalog structure, markdown rendering (all 8 rows, status icons, detail lines, regenerate hint), and JSON aggregation
- `tests/semantic/conftest.py`: `pytest_runtest_makereport` hook collecting node id + outcome; `pytest_sessionfinish` writes `reports/semantic/results.json` for cross-tier ingestion
- `pyproject.toml`: `report` optional extra (`allure-pytest>=2.13.0`, `markdown>=3.6`); mypy overrides for `markdown.*` and `allure.*`
- `scripts/build_report_site.py`: assembles `site/` from committed Markdown artifacts — defects-caught → `index.html`, calibration → `calibration.html`, cost summary → `cost.html`, seeded-defects → `vulnerabilities.html`; copies Allure HTML to `site/allure/` when present; placeholder pages when artifacts are absent
- `tests/unit/test_report_site.py`: 8 unit tests covering site dir creation, page generation routing, allure placeholder, nav link completeness
- `.github/workflows/pages.yml`: triggers on push to main, `workflow_dispatch`, and `workflow_run` after Semantic/Adversarial; runs hermetic suites with `--alluredir`, downloads live artifacts via `dawidd6/action-download-artifact` (continue-on-error), generates defects-caught, builds Allure HTML, assembles `site/`, deploys to GitHub Pages
- `semantic-eval.yml`: replaced placeholder "Summarize cost" step — pytest now runs with `--alluredir`; cost summary written to `$GITHUB_STEP_SUMMARY`; reports artifact uploaded
- `adversarial.yml`: hermetic suite runs with `--alluredir`; Allure results artifact uploaded for Pages ingestion
- `README.md`: PR Gate, Semantic Eval, and Adversarial CI badge row; MIT and Python 3.12 metadata badges
- `.gitignore`: `site/` added

### Added — Project Foundation
- Repo scaffold: src layout, pyproject.toml, uv, ruff, mypy strict, pre-commit
- `verity.config`: Pydantic-settings config for provider, judge, retrieval
- `verity.providers`: LiteLLM wrapper routing to Z.ai / OpenRouter / Together
- `verity.cost`: token/cost accounting with per-run accumulator
- CI skeleton: `pr-gate.yml` (Tier 1 — lint, type, unit; no live calls)
- Makefile with task entrypoints; `.env.example`

### Added — Observability & Cost Tracking
- `verity.tracing`: `_ENABLED` flag gated on `VERITY_TRACING` env (default off); `init_tracing(service_name)` initialises SDK `TracerProvider` with console/file/OTLP exporters; `traced(name, **attrs)` context manager yielding a real span or `None` when disabled; `record_call_span(call_record)` attaches model/token/cost attributes to the current span; file exporter writes JSONL to `reports/traces/`
- `verity.reporting`: `render_cost_summary(accumulator)` → per-label markdown table (calls, prompt tok, completion tok, total tok, cost USD + grand totals); `write_step_summary(text)` → `$GITHUB_STEP_SUMMARY` in CI, `reports/cost-summary.md` locally
- `sut.agent.CoverageAgent.answer`: wrapped in `agent.answer` span with `retrieval` and `tool.coverage_calculator` child spans; no-op when tracing disabled
- `verity.providers.LLMProvider.complete` + `_result_from_payload`: call `record_call_span()` after every `log_call()` to attach LLM attributes to the current span — covers both SUT and judge calls
- `tests/adversarial/conftest.py` + `tests/semantic/conftest.py`: shared session `RunAccumulator` and `pytest_sessionfinish()` hook writing the cost summary; even cassette-replay runs produce a cost table
- `scripts/trace_demo.py`: one-shot demo running hermetic agent with `VERITY_TRACING=1` and file exporter, producing `reports/traces/spans-<ts>.jsonl` — no API key required
- `Makefile`: `make trace-demo` target
- `pyproject.toml`: `otel` optional dependency group (`opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc`); mypy override for `opentelemetry.*`
- 5 unit tests in `tests/unit/test_tracing.py` covering no-op path, init, `record_call_span`, and real span + attribute propagation via in-memory exporter
- `docs/observability.md`: tracing architecture, span table, env vars, cost summary, CI integration, OTel extra install
- `.env.example`: tracing env vars added

### Added — Adversarial Red-Team Tier
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

### Added — Judge Calibration & Self-Bias Measurement
- `verity.calibration`: `CalibrationCase` Pydantic schema; `load_calibration()`; `AgreementReport` + `SelfBiasReport` frozen dataclasses; `compute_agreement()` (raw %, Cohen's kappa, per-metric MAE); `compute_self_bias()` (delta = E[judge−human | glm] − E[judge−human | other]); `build_scoring_prompt()`, `parse_judge_score()`, `score_case()`, `score_all()` for rubric-based scoring
- `verity.metrics.rubrics`: added `FAITHFULNESS_RUBRIC` (calibration reuses all four Tier-2 rubrics)
- `verity.judges`: `ProviderJudge` now propagates `cassette_mode` + `cassette_dir` into internal judge `Settings`, enabling calibration cassette replay
- `datasets/calibration/labeled.yaml`: 32 human-annotated cases — 8 per metric (completeness, disambiguation, refusal, faithfulness), 16 GLM-family / 16 other-family for self-preference measurement
- `datasets/calibration/cassettes/`: 32 SHA-256-keyed authored judge-score cassettes for hermetic replay with no API key
- `scripts/run_calibration.py`: three-mode runner (author, record-live, replay); markdown report + JSON artifact output
- `docs/calibration-report.md`: committed report — raw agreement 96.9%, Cohen's kappa 0.934, MAE 0.028; self-preference delta +0.056 (GLM outputs scored 0.056 higher than human on average); per-metric breakdown and threshold traceability
- `Makefile`: `make calibrate` (hermetic, no key) and `make calibrate-live` (live recording) targets
- 40 unit tests covering schema validation, loader, agreement/kappa/MAE, self-bias delta, prompt builder, and score parser edge cases

### Added — Semantic Evaluation Tier
- `pyproject.toml`: optional `semantic` dependency group (`deepeval>=1.5.0`, `ragas>=0.2.0`); mypy overrides for third-party typed/untyped packages
- `verity.judges`: `ProviderJudge` wraps `LLMProvider` for plug-and-play judge routing; `DeepEvalJudge` adapter (lazy `DeepEvalBaseLLM` subclass); `RagasJudge` duck-type LangChain shim (avoids `langchain_community` import error)
- `verity.metrics.rubrics`: three G-Eval rubric texts — completeness (#3 multi-hop), disambiguation (#4 contradiction), refusal-boundary (#6 medical advice)
- `verity.metrics.deepeval_metrics`: six metric factory functions with per-metric thresholds; lazy deepeval import (only when metric is constructed); `make_hallucination`, `make_answer_relevancy`, `make_completeness`, `make_disambiguation`, `make_refusal_geval`, `make_tool_correctness`
- `verity.metrics.ragas_metrics`: three RAGAS metric factories with per-metric thresholds — `make_faithfulness`, `make_context_precision`, `make_ragas_answer_relevancy`
- `verity.statistics`: `StatResult` frozen dataclass; `run_n_samples(fn, n)` runs a scoring function N times; `aggregate(scores)` → mean/median/stdev/pass_rate; `threshold_pass(stat, threshold, mode)` — modes: mean, median, pass_rate, all
- `tests/semantic/`: 6-file Tier-2 suite (conftest + faithfulness, completeness, disambiguation, tool-use, refusal, relevancy); all marked `semantic`+`live`; clean cases assert score ≥ threshold; defect cases assert score < threshold (defect detected = green test); auto-skips when no API key is configured
- `.github/workflows/semantic-eval.yml`: triggers on push to main, nightly at 02:00 UTC, and `workflow_dispatch`; no-ops gracefully when no API key secret is set; installs semantic extras, indexes corpus, runs semantic suite
- `docs/thresholds.md`: per-metric threshold table with defect coverage map, statistical method description, and rationale for each threshold value

### Added — Deterministic Evaluation Tier
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

### Added — Policy Coverage Copilot (System Under Test)
- Fictional corpus: `bronze.md`, `silver.md`, `gold.md`, `definitions.md`, `exclusions.md`, `amendments.md`
- All 8 seeded defects baked into corpus and SUT code
- `sut.tools.coverage_calculator`: deterministic Pydantic-typed cost calculator + tool schema
- `sut.retriever`: Chroma + built-in ONNX embeddings, markdown-aware chunker
- `sut.guardrails`: input scope check + output PII scrubber (with intentional seeded gaps)
- `sut.agent`: full agent loop with tool-use, citations, structured `AgentResponse`
- Unit tests: coverage calculator, guardrails, retriever chunker, config, cost, providers (mocked)
- `docs/seeded-defects.md`: living catalog of all 8 seeded defects
