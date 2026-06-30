# ADR-0004: Judge Calibration and Self-Bias Measurement

**Status:** Accepted

## Context

Tier-2 semantic evaluation uses GLM-5.2 as both the SUT runtime model and
the judge model. This creates a **self-preference risk**: an LLM judge may
systematically rate outputs from its own model family more favorably than
outputs from other model families, inflating agreement numbers.

Before trusting the judge's scores as a reliable signal, two questions must
be answered:

1. How well does the judge agree with human annotators?
2. Does the judge exhibit self-preference bias that would invalidate its scores
   when evaluating GLM-generated outputs?

## Decision

Implement a **judge calibration suite** in `verity/calibration.py` with:

- **32 human-annotated calibration cases** in `datasets/calibration/labeled.yaml`:
  - 8 cases per metric (completeness, disambiguation, refusal, faithfulness).
  - Split 50/50 by model family: 16 GLM-family outputs, 16 other-family outputs.
  - Human scores on the same 0-10 rubric used by G-Eval.
- **`compute_agreement()`**: raw percentage, Cohen's kappa (chance-adjusted),
  and per-metric MAE between judge scores and human labels.
- **`compute_self_bias()`**: delta = E[judge-human | GLM outputs] - E[judge-human | other outputs].
  A positive delta means the judge scores GLM outputs higher than humans do
  relative to how it scores other-family outputs.
- **Hermetic replay**: 32 authored cassettes in `datasets/calibration/cassettes/`
  allow `make calibrate` to run the full suite with zero API calls.
- **Committed report** at `docs/calibration-report.md` (mirrors the cassette-report
  precedent of `docs/defects-caught.md`).

### Measured Results (committed report)

| Metric | Value |
|--------|-------|
| Raw agreement | 96.9% |
| Cohen's kappa | 0.934 (almost perfect) |
| Per-metric MAE | 0.028 |
| Self-preference delta | +0.056 (GLM outputs scored 0.056 higher on average) |

The self-preference bias of +0.056 on a 0-10 scale is small and within the
tolerance of the per-metric thresholds (all gaps are >= 0.5 between
pass/fail thresholds). The judge is considered reliable for this suite.

## Consequences

**Easier:**
- The calibration report provides a traceable, human-readable justification for
  trusting the judge's scores.
- If the judge model changes (e.g., upgrade to GLM-6), the calibration suite
  can be re-run (`make calibrate-live`) and the delta re-measured.
- The self-bias delta is a number, not a claim — it can be cited in arguments
  about eval reliability.

**Harder:**
- Calibration adds 32 hand-authored cases and cassettes to maintain.
- If the rubric text changes, existing human labels may no longer match the
  new prompt, requiring re-annotation.

## Alternatives Considered

| Alternative | Rejected because |
|-------------|-----------------|
| Skip calibration, trust the judge | Cannot quantify or defend the "judge trust" competency claim |
| Use a different model as judge | Adds a second provider dependency; self-bias still exists and is unmeasured |
| Inter-annotator agreement only | Does not isolate self-preference from general judge quality |
