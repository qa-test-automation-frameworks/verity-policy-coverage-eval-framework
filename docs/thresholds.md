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
   (default N=1 for local and push runs; the nightly scheduled semantic run
   sets N=5 — see `semantic-eval.yml`).
2. **Aggregate** — compute mean, median, stdev, and pass-rate (fraction of
   individual runs that exceeded the threshold).
3. **Threshold mode** — the comparison is made at the distribution level:
   - `mean`: `stat.mean >= threshold` (default for most metrics)
   - `median`: resistant to outlier runs
   - `pass_rate`: `stat.pass_rate >= threshold` (useful for high-variance judges)
   - `all`: mean AND median AND pass_rate all ≥ threshold (strictest)
4. **Pass-rate interval** — sampled semantic runs (`N > 1`) report
   `pass_rate_wilson_interval(stat)` beside the point estimate in failure messages and
   `reports/semantic/results.json`, which is especially useful for scheduled runs with
   small sample counts.

See `verity/statistics.py` for the implementation.

> **Committed judge-calibration artifact:** `docs/calibration-report.md`
> is a 56-case, 7-metric synthetic replay that demonstrates the agreement,
> kappa, MAE, and self-preference calculations without live API spend. It is
> not a live judge distribution. Run `make calibrate-live` with the configured
> judge key before treating these thresholds as measured judge-performance
> thresholds.

---

## Thresholds

### DeepEval metrics

| Metric | Constant | Threshold | Mode | Targets defect(s) | Calibration |
|---|---|---|---|---|---|
| Hallucination | `THRESHOLD_HALLUCINATION` | 0.50 | mean | #1, #7 | synthetic PASS (88% agreement) |
| Answer Relevancy | `THRESHOLD_ANSWER_RELEVANCY` | 0.70 | mean | — (baseline) | synthetic PASS (100% agreement) |
| G-Eval Completeness | `THRESHOLD_COMPLETENESS` | 0.70 | mean | #3 | synthetic PASS (100% agreement) |
| G-Eval Disambiguation | `THRESHOLD_DISAMBIGUATION` | 0.60 | mean | #4 | synthetic PASS (100% agreement) |
| G-Eval Refusal | `THRESHOLD_REFUSAL` | 0.70 | mean | #6 | synthetic PASS (100% agreement) |
| Tool Correctness (optional factory) | `THRESHOLD_TOOL_CORRECTNESS` | 0.60 | mean | #5 | not yet run |

Hallucination (DeepEval) is scored as the fraction of claims NOT grounded in
context, so a passing test means `score < 0.5` (low hallucination rate). Clean
cases are expected to score well above this; defect cases should score ≥ 0.5.
The synthetic calibration data keeps the legacy case label `hallucination`, but its
0–10 rubric score is normalized as `hallucination_groundedness` (10 = fully grounded).
That higher-is-better rubric result is not the raw DeepEval metric.

### RAGAS metrics

| Metric | Constant | Threshold | Mode | Targets defect(s) | Calibration |
|---|---|---|---|---|---|
| Faithfulness | `THRESHOLD_FAITHFULNESS` | 0.70 | mean | #1, #7 | synthetic PASS (88% agreement) |
| Context Precision | `THRESHOLD_CONTEXT_PRECISION` | 0.60 | mean | — (retrieval health) | synthetic PASS (100% agreement) |
| Answer Relevancy | `THRESHOLD_ANSWER_RELEVANCY` | 0.70 | mean | — (baseline) | synthetic PASS (100% agreement) |

Faithfulness measures whether answer claims are supported by retrieved passages. It cannot
establish that a supported passage is current: a response that repeats the superseded `$420`
value from `silver.md` can still be faithful to its context. Defect #2 therefore uses the
separate deterministic `check_temporal_amount` oracle against the authored `$445` amendment.
Its `PASS` / `FAIL` / `REVIEW` result is recorded independently; only temporal `PASS` can mark
the stale-premium behavior `NOT_REPRODUCED`, while `REVIEW` remains `UNRESOLVED`.

The Calibration column reflects `docs/calibration-report.md`'s per-metric breakdown.
`not yet run` means the metric has no dedicated calibration cases in
`datasets/calibration/labeled.yaml` at all. `synthetic PASS` means 8 calibration
cases exist for the metric and the committed authored-score replay clears the
agreement/MAE bar. It is still conservative-by-convention rather than a live
judge-performance measurement until `make calibrate-live` is run with the
configured judge and committed as a live report.

**Control-case gating on faithfulness and answer relevancy is quarantined**
(`@pytest.mark.quarantine` on `test_clean_faithfulness` in
`tests/semantic/test_faithfulness.py` and `test_answer_relevancy` in
`tests/semantic/test_relevancy.py`) — both tests still run and report signal,
but a failure on either does not block a merge, since the live control
failures below have not yet been cleared by a fresh live calibration/control
run. Defect-detection gating (`test_defect_faithfulness_detected`) is
unaffected. See `docs/known-issues.md` (KI-3) for the tracked entry.

---

## Committed live run: control-case failures

The committed `reports/semantic/results.json` run (`openrouter/openai/gpt-4o-mini` as both
SUT and judge — see README Limitations) has 10 of 40 control-tier test nodes failing,
listed in the "Control-Case Results" section of `docs/defects-caught.md`. All 10 are
faithfulness or answer-relevancy assertions. The 75% faithfulness agreement and 0.238 MAE
belong to a separate historical live rubric-calibration report generated 2026-07-02 with
32 cases and `openrouter/openai/gpt-4o-mini`; that dated report is preserved at
`reports/calibration/archive/live-2026-07-02/calibration-report.md`. The current
`docs/calibration-report.md` is a 56-case synthetic replay generated 2026-07-04; its 88%
faithfulness agreement and 0.025 MAE are authored-score demonstration values, not a fresh
live measurement and not directly comparable to the historical report. The old semantic
control failures and the historical rubric result remain separate signals with incomplete
run metadata. Re-run `make eval-semantic` and `make calibrate-live` with a configured
provider before claiming a current live result.

---

## Threshold rationale

Thresholds are intentionally conservative rather than calibrated — the goal is
to detect large regressions (catching baked-in defects) rather than micro-tune
precision. The next threshold-hardening step is to replace these convention-based
defaults with calibrated values from the configured judge model's measured score
distribution.

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
| #2 Stale context (premium) | Temporal amount oracle | Faithfulness (grounding only) |
| #3 Multi-hop calculation | — | G-Eval Completeness |
| #4 Contradiction not surfaced | — | G-Eval Disambiguation |
| #5 Tool arg transposition | `check_tool_args` | Task Completion |
| #6 Refusal boundary breach | `check_refusal` | G-Eval Refusal |
| #7 Prompt injection | `check_injection` | Faithfulness, Hallucination |
| #8 PII leakage | `scan_pii` / `check_pii` | — |
