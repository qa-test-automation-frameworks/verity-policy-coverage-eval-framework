# ADR-0004: Judge Calibration and Self-Bias Measurement

**Status:** Accepted as methodology; empirical live calibration pending

## Context

Tier-2 semantic evaluation uses GLM-4.5 as both the SUT runtime model and
the judge model. This creates a **self-preference risk**: an LLM judge may
systematically rate outputs from its own model family more favorably than
outputs from other model families, inflating agreement numbers.

Before trusting the judge's scores as a reliable signal in live operation, two questions must be answered with real judge outputs:

1. How well does the judge agree with human annotators?
2. Does the judge exhibit self-preference bias that would invalidate its scores
   when evaluating GLM-generated outputs?

## Decision

Implement a **judge calibration suite** in `verity/calibration.py` with:

- **32 synthetic-label calibration cases** in `datasets/calibration/labeled.yaml`:
  - 8 cases per metric (completeness, disambiguation, refusal, faithfulness).
  - Split 50/50 by model family: 16 GLM-family outputs, 16 other-family outputs.
  - Reference scores on the same 0-10 rubric used by G-Eval.
- **`compute_agreement()`**: raw percentage, Cohen's kappa (chance-adjusted),
  and per-metric MAE between judge scores and human labels.
- **`compute_self_bias()`**: delta = E[judge-human | GLM outputs] - E[judge-human | other outputs].
  A positive delta means the judge scores GLM outputs higher than humans do
  relative to how it scores other-family outputs.
- **Hermetic replay**: 32 authored cassettes in `datasets/calibration/cassettes/`
  allow `make calibrate` to run the full suite with zero API calls.
- **Committed report** at `docs/calibration-report.md` (mirrors the cassette-report
  precedent of `docs/defects-caught.md`).

### Synthetic Replay Results (committed report)

| Metric | Value |
|--------|-------|
| Raw agreement | 96.9% on synthetic labels |
| Cohen's kappa | 0.934 on synthetic labels |
| Per-metric MAE | 0.028 |
| Self-preference delta | +0.056 on synthetic labels |

These values demonstrate that the calibration code path, reporting, and replay fixtures work. They are not evidence that the live judge is reliable; run `make calibrate-live` with a real judge and a genuine second model family before using the numbers to justify thresholds.

## Consequences

**Easier:**
- The calibration report provides a traceable, human-readable example of how judge trust should be evaluated.
- If the judge model changes (e.g., upgrade to GLM-6), the calibration suite
  can be run (`make calibrate-live`) and the delta measured on live outputs.
- The self-bias calculation is explicit, so live results can be reviewed instead of inferred.

**Harder:**
- Calibration adds 32 synthetic-label cases and cassettes to maintain.
- If the rubric text changes, existing human labels may no longer match the
  new prompt, requiring re-annotation.

## Alternatives Considered

| Alternative | Rejected because |
|-------------|-----------------|
| Skip calibration, trust the judge | Cannot quantify or defend judge reliability |
| Use a different model as judge | Adds a second provider dependency; self-bias still exists and is unmeasured |
| Inter-annotator agreement only | Does not isolate self-preference from general judge quality |
