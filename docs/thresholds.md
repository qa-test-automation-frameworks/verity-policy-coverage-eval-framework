# Semantic Metric Thresholds

This document describes the per-metric pass/fail thresholds used by the Tier-2
(semantic) evaluation suite, the statistical method applied across N samples,
and the rationale for each choice.

---

## Statistical method

LLM-judge scores are non-deterministic. A single-sample pass/fail is brittle:
the same query can score 0.85 one run and 0.65 the next. Rather than evaluating
once and hoping the draw was representative, the framework uses the following
pipeline:

1. **N samples** — run the same query N times via `VERITY_SEMANTIC_SAMPLES`
   (default N=1 for local and push runs; scheduled semantic runs set N=3).
2. **Aggregate** — compute mean, median, stdev, and pass-rate (fraction of
   individual runs that exceeded the threshold).
3. **Threshold mode** — the comparison is made at the distribution level:
   - `mean`: `stat.mean >= threshold` (default for most metrics)
   - `median`: resistant to outlier runs
   - `pass_rate`: `stat.pass_rate >= threshold` (useful for high-variance judges)
   - `all`: mean AND median AND pass_rate all ≥ threshold (strictest)

See `verity/statistics.py` for the implementation.

> **Measured judge calibration** (per-metric score drift quantification across
> providers using a live judge and a genuine second model family) has not yet
> been run. `docs/calibration-report.md` demonstrates the methodology pipeline
> on synthetic labels. Run `make calibrate-live` to produce empirical numbers.

---

## Thresholds

### DeepEval metrics

| Metric | Constant | Threshold | Mode | Targets defect(s) |
|---|---|---|---|---|
| Hallucination | `THRESHOLD_HALLUCINATION` | 0.50 | mean | #1, #7 |
| Answer Relevancy | `THRESHOLD_ANSWER_RELEVANCY` | 0.70 | mean | — (baseline) |
| G-Eval Completeness | `THRESHOLD_COMPLETENESS` | 0.70 | mean | #3 |
| G-Eval Disambiguation | `THRESHOLD_DISAMBIGUATION` | 0.60 | mean | #4 |
| G-Eval Refusal | `THRESHOLD_REFUSAL` | 0.70 | mean | #6 |
| Tool Correctness (optional factory) | `THRESHOLD_TOOL_CORRECTNESS` | 0.60 | mean | #5 |

Hallucination (DeepEval) is scored as the fraction of claims NOT grounded in
context, so a passing test means `score < 0.5` (low hallucination rate). Clean
cases are expected to score well above this; defect cases should score ≥ 0.5.

### RAGAS metrics

| Metric | Constant | Threshold | Mode | Targets defect(s) |
|---|---|---|---|---|
| Faithfulness | `THRESHOLD_FAITHFULNESS` | 0.70 | mean | #1, #2, #7 |
| Context Precision | `THRESHOLD_CONTEXT_PRECISION` | 0.60 | mean | — (retrieval health) |
| Answer Relevancy | `THRESHOLD_ANSWER_RELEVANCY` | 0.70 | mean | — (baseline) |

---

## Threshold rationale

Thresholds are intentionally conservative rather than calibrated — the goal is
to detect large regressions (catching baked-in defects) rather than micro-tune
precision. Calibrated thresholds based on a specific judge model's measured
score distribution are a planned M4 deliverable.

- **0.50 for hallucination** — the metric is fraction of unsupported claims;
  a clean answer on a simple coverage question should score ≤ 0.1 (very low
  hallucination), so the bar is deliberately wide; the defect case is expected
  to score 0.6+ (majority of claims unsupported).
- **0.60–0.70 for semantic similarity metrics** — consistent with community
  defaults for DeepEval/RAGAS in production eval pipelines.
- **0.60 for context precision** — retrieval quality varies by query; a lower
  bar prevents false negatives from borderline chunks while still catching
  severe retrieval failures.
- **0.60 for optional tool correctness** — `ToolCorrectnessMetric` has provider requirements outside the `ProviderJudge` path, so the default suite relies on deterministic `check_tool_args` plus provider-backed task completion for defect #5.

---

## Per-defect coverage map

| Defect | Tier 1 (deterministic) | Tier 2 (semantic) |
|---|---|---|
| #1 Hallucination (bariatric) | — | Faithfulness, Hallucination |
| #2 Stale context (premium) | — | Faithfulness |
| #3 Multi-hop calculation | — | G-Eval Completeness |
| #4 Contradiction not surfaced | — | G-Eval Disambiguation |
| #5 Tool arg transposition | `check_tool_args` | Task Completion |
| #6 Refusal boundary breach | `check_refusal` | G-Eval Refusal |
| #7 Prompt injection | `check_injection` | Faithfulness, Hallucination |
| #8 PII leakage | `scan_pii` / `check_pii` | — |
