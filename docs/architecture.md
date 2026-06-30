# Architecture

This document describes the system structure, data flow, and design rationale
of the verity policy-coverage evaluation framework.

---

## System Overview

The framework is a two-package Python monorepo:

| Package | Role |
|---------|------|
| `src/verity/` | The reusable evaluation framework (config, providers, cost, cassettes, golden, checks, statistics, metrics, judges, calibration, adversarial, tracing, reporting) |
| `src/sut/` | The System Under Test — Policy Coverage Copilot, a RAG + tool-use assistant with 8 intentionally seeded defects |

The SUT is the target; the framework is the portfolio artifact.

---

## Three-Layer Eval Pyramid

```
┌─────────────────────────────────────────────────────────────────┐
│  Tier 3 — Adversarial (weekly)                                  │
│  Promptfoo/DeepTeam: injection, jailbreak, PII probes           │
│  Non-blocking; produces vulnerability report                    │
├─────────────────────────────────────────────────────────────────┤
│  Tier 2 — Semantic (nightly / push to main)                     │
│  DeepEval + RAGAS over versioned golden dataset                 │
│  Statistical thresholds; GLM-5.2 judge; cost-tracked            │
├─────────────────────────────────────────────────────────────────┤
│  Tier 1 — Deterministic (every PR)                              │
│  Schema checks; guardrail assertions; cassette replay           │
│  No live API calls; < 3 min; blocks merge                       │
└─────────────────────────────────────────────────────────────────┘
```

Each tier has a different cost profile, latency, and failure-signal richness.
See [ADR-0002](adr/0002-three-layer-eval-pyramid.md) for the rationale.

---

## Component Walk-Through

### `src/verity/`

| Module | Responsibility |
|--------|---------------|
| `config.py` | Pydantic-settings root config (`Settings`), sub-configs for provider, judge, retrieval, and cassette mode |
| `providers.py` | `LLMProvider` wrapping LiteLLM; cassette record/replay path; cost accounting via `RunAccumulator`; span recording via `record_call_span()` |
| `cost.py` | `Usage`, `Cost`, `CallRecord`, `RunAccumulator`; per-label token and cost accounting; price table keyed by model slug |
| `cassettes.py` | SHA-256 keyed cassette library; `request_key(messages, model, tools)` deterministic hash; `CassetteMissError` on replay miss |
| `golden.py` | `GoldenCase` Pydantic schema (query, member_id, behavior, ground_truth, must_contain, expected_tool, defect_id, ...); `load_golden()` YAML loader |
| `checks.py` | Pure deterministic assertion functions: `validate_response_schema`, `check_refusal`, `check_human_review`, `check_tool_args`, `scan_pii`, `check_pii`, `scan_injection`, `check_injection`, `check_must_contain`, `check_must_not_contain` |
| `statistics.py` | `run_n_samples(fn, n)`, `aggregate(scores)` (mean/median/stdev/pass_rate), `threshold_pass(stat, threshold, mode)` |
| `metrics/rubrics.py` | G-Eval rubric text constants for completeness (#3), disambiguation (#4), refusal (#6), and faithfulness |
| `metrics/deepeval_metrics.py` | Six lazy metric factories: hallucination, answer relevancy, completeness, disambiguation, refusal, optional tool correctness |
| `metrics/ragas_metrics.py` | Three RAGAS metric factories: faithfulness, context precision, answer relevancy |
| `judges.py` | `ProviderJudge` (routes to `LLMProvider`); `DeepEvalJudge` adapter; `RagasJudge` LangChain duck-type shim |
| `calibration.py` | `CalibrationCase` schema; `compute_agreement()` (raw %, Cohen's kappa, MAE); `compute_self_bias()` (GLM vs other delta); `score_all()` via rubric scoring prompt |
| `adversarial.py` | `AdversarialProbe` Pydantic schema (category, defense, expected_outcome, must_not_contain, retrieval_fixture_id); `load_probes()` |
| `tracing.py` | `_ENABLED` flag gated on `VERITY_TRACING` env; `init_tracing()` SDK TracerProvider; `traced(name, **attrs)` context manager (no-op when disabled); `record_call_span(call_record)` attaches llm.* attributes |
| `reporting.py` | `render_cost_summary(accumulator)` -> per-label markdown table; `write_step_summary(text)` -> `$GITHUB_STEP_SUMMARY` or `reports/cost-summary.md` |

### `src/sut/`

| Module | Responsibility |
|--------|---------------|
| `corpus/` | 6 Markdown policy documents (bronze, silver, gold, definitions, exclusions, amendments) with 8 seeded defects baked in |
| `data/members.yaml` | Synthetic member registry (MBR-001 through MBR-005) — fictional, no real PII |
| `retriever.py` | `PolicyRetriever` (Chroma + ONNX embeddings, markdown-aware chunker, 160-word chunks / top-3 default); `FixtureRetriever` (drop-in from JSON files, no Chroma required for Tier 1) |
| `tools/coverage_calculator.py` | Deterministic Pydantic-typed cost calculator + `COVERAGE_CALCULATOR_SCHEMA`; tool arguments intentionally ambiguously named (seeded defect #5) |
| `guardrails.py` | `check_input_scope()` (regex `_OUT_OF_SCOPE_PATTERNS`; gap = seeded defect #6); `scrub_output()` (masks member-id and date patterns); `log_member_context()` (naive DEBUG logging = seeded defect #8) |
| `agent.py` | `CoverageAgent.answer()`: load member, check scope, retrieve chunks, first LLM turn, optional tool-use second turn, scrub output; wraps all spans via `traced()` |

---

## `agent.answer()` Data Flow

```
agent.answer(query, member_id)
|
+-- [span: agent.answer]
|   +-- guardrails.check_input_scope(query)     # defect #6 gap here
|   +-- [span: retrieval]
|   |   \-- retriever.retrieve(query, top_k)   # returns Chunk list
|   |
|   +-- provider.complete(messages, ...)        # first LLM turn
|   |   +-- cassette replay / live call
|   |   +-- accumulator.log_call(...)           # cost accounting
|   |   \-- record_call_span(call_record)       # OTel attributes
|   |
|   +-- [if tool_call in response]
|   |   +-- [span: tool.coverage_calculator]
|   |   |   \-- run_coverage_calculator(args)  # deterministic
|   |   \-- provider.complete(messages + tool_result, ...)  # second turn
|   |       +-- cassette replay / live call
|   |       +-- accumulator.log_call(...)
|   |       \-- record_call_span(call_record)
|   |
|   \-- guardrails.scrub_output(answer)         # defect #8 gap here
|
\-- AgentResponse(answer, citations, tool_invocations, refused, requires_human_review, ...)
```

---

## CI Tier / Trigger Table

| Workflow | Trigger | Tiers | Key Constraint |
|----------|---------|-------|----------------|
| `pr-gate.yml` | Every PR | 1 (unit + deterministic) | No live calls; must pass to merge |
| `semantic-eval.yml` | Push to main + nightly | 2 (semantic) | Key-gated; no-op without secret |
| `adversarial.yml` | Weekly + on-demand | 3 (adversarial) | Hermetic always; Promptfoo/calibrate key-gated |
| `pages.yml` | Push to main + workflow_run | 1+2+3 (reports) | Hermetic build always; ingests live artifacts |

---

## Key Design Decisions

See `docs/adr/` for full records. Summary:

| ADR | Decision | Consequence |
|-----|----------|-------------|
| [0001](adr/0001-glm-5-2-model-choice.md) | GLM-5.2 via LiteLLM | OpenAI-compat; swap provider without code change |
| [0002](adr/0002-three-layer-eval-pyramid.md) | Three eval tiers | Cost/speed/signal balanced across PR/nightly/weekly cadence |
| [0003](adr/0003-cassette-replay-for-ci.md) | SHA-256 cassette replay | Zero live calls in PR gate; deterministic; fast |
| [0004](adr/0004-judge-calibration-and-self-bias.md) | Judge calibration + self-bias | Methodology demonstrated on synthetic labels; live measurement pending |
| [0005](adr/0005-statistical-thresholds.md) | Distribution-over-N thresholds | Eliminates flakiness from LLM non-determinism |

---

## Related Docs

- [docs/seeded-defects.md](seeded-defects.md) - all 8 defects, where baked in, and caught-by reference
- [docs/defects-caught.md](defects-caught.md) - hermetic proof matrix (regenerate: `make defects-report`)
- [docs/thresholds.md](thresholds.md) - per-metric threshold table with defect coverage map
- [docs/calibration-report.md](calibration-report.md) - synthetic-label calibration methodology report
- [docs/observability.md](observability.md) - tracing architecture, span table, env vars
- [docs/adr/](adr/) - architecture decision records
