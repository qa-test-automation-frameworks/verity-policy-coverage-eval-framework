# ADR-0004: Judge Calibration and Self-Bias Measurement

**Status:** Accepted; live calibration measured 2026-07-02 (see below)

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

### Live Calibration Results (committed report)

Measured 2026-07-02 with `VERITY_JUDGE_PROVIDER=openrouter VERITY_JUDGE_MODEL=openai/gpt-4o-mini`
(not the GLM-4.5 default in this ADR's original context — see `docs/calibration-report.md` and
the README Limitations section for why):

| Metric | Value |
|--------|-------|
| Raw agreement | 93.8% |
| Cohen's kappa | 0.870 |
| Per-metric MAE | 0.125 |
| Self-preference delta | -0.037 (own family = "other", i.e. non-GLM) |

These are real measurements against live judge calls, not synthetic replay — see
`docs/calibration-report.md` for the full per-case breakdown. Cohen's kappa (0.870) and raw
agreement (93.8%) both clear this ADR's original acceptance bar (kappa ≥ 0.60, agreement ≥ 85%).
This calibration path uses the shared rubric text through `verity.calibration.build_scoring_prompt()`;
Tier-2 DeepEval and RAGAS adapters wrap similar rubric intent in their own runtime prompt and
score-extraction paths, so adapter-level calibration remains a separate validation step.
The self-preference delta is small and negative for this judge/family pairing; re-run
`make calibrate-live` with a GLM-4.5 judge key to measure genuine GLM self-preference, which
this run could not — the judge here was gpt-4o-mini, not GLM.

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
