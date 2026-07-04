# Judge Calibration Report

> **Note:** This report replays committed cassettes containing
> hand-authored judge scores — it is a synthetic demonstration of the
> calibration methodology (dataset, agreement statistics, self-bias
> calculation, and report rendering), not a measurement of a live judge.
> Both the candidate outputs/human labels in
> `datasets/calibration/labeled.yaml` and the judge scores replayed here
> are hand-authored. Run `make calibrate-live` with a configured API key
> to produce a report against a real judge.

**Generated:** 2026-07-04  
**Judge model:** `openai/glm-4.5`  
**Dataset:** `datasets/calibration/labeled.yaml` (56 cases)  
**Mode:** synthetic replay (authored scores)

---

## Agreement with Human Labels

| Metric | Value |
|--------|-------|
| Raw agreement | **96.4%** |
| Cohen's kappa | **0.926** |
| MAE (0-1 scale) | **0.025** |
| N | 56 |

### Per-metric breakdown

| Metric | N | Raw agreement | MAE | Status |
|--------|---|---------------|-----|--------|
| answer_relevancy | 8 | 100% | 0.012 | PASS |
| completeness | 8 | 100% | 0.013 | PASS |
| context_precision | 8 | 100% | 0.038 | PASS |
| disambiguation | 8 | 100% | 0.037 | PASS |
| faithfulness | 8 | 88% | 0.025 | PASS |
| hallucination | 8 | 88% | 0.012 | PASS |
| refusal | 8 | 100% | 0.037 | PASS |

---

## Self-Preference Bias

Self-preference delta measures whether the judge inflates scores for outputs from its own model family (GLM) compared to outputs from other families.

| Family | N | Mean Δ (judge - human) |
|--------|---|------------------------|
| GLM (own family) | 28 | **+0.043** |
| Other family | 28 | **+0.007** |
| **Self-preference delta** | — | **+0.036** |

> Negligible self-preference bias (|delta| < 0.05). Thresholds are not materially affected.

---

## Threshold Traceability

The semantic tier thresholds in `docs/thresholds.md` are informed by this synthetic methodology demonstration; they are not yet backed by a measured live judge distribution:

- **Raw agreement ≥ 85%**: this synthetic run shows 96.4%.
- **Cohen's kappa ≥ 0.60** (substantial agreement): synthetic kappa = 0.926.
- **Self-preference delta**: +0.036 — see interpretation above.

See [`docs/thresholds.md`](thresholds.md) for per-metric threshold values and the statistical method used.

> Scope note: this calibration path scores the shared rubric text through
> `verity.calibration.build_scoring_prompt()`. Tier-2 DeepEval and RAGAS
> adapters wrap those rubrics in their own prompt and parsing paths, so
> this report measures judge/rubric agreement rather than every runtime
> metric adapter end to end.

---

## Individual Case Scores

| Case ID | Metric | Family | Human | Judge | Δ | Agreement |
|---------|--------|--------|-------|-------|---|-----------|
| `calib-completeness-001` | completeness | glm | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-completeness-002` | completeness | glm | 0.3 | 0.4 | +0.1 | ✓ |
| `calib-completeness-003` | completeness | other | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-completeness-004` | completeness | other | 0.1 | 0.1 | +0.0 | ✓ |
| `calib-completeness-005` | completeness | glm | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-completeness-006` | completeness | other | 0.2 | 0.2 | +0.0 | ✓ |
| `calib-completeness-007` | completeness | glm | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-completeness-008` | completeness | other | 0.1 | 0.1 | +0.0 | ✓ |
| `calib-disambiguation-001` | disambiguation | glm | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-disambiguation-002` | disambiguation | glm | 0.3 | 0.4 | +0.1 | ✓ |
| `calib-disambiguation-003` | disambiguation | other | 0.9 | 0.9 | +0.0 | ✓ |
| `calib-disambiguation-004` | disambiguation | other | 0.0 | 0.0 | +0.0 | ✓ |
| `calib-disambiguation-005` | disambiguation | glm | 0.8 | 0.9 | +0.1 | ✓ |
| `calib-disambiguation-006` | disambiguation | other | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-disambiguation-007` | disambiguation | glm | 0.2 | 0.3 | +0.1 | ✓ |
| `calib-disambiguation-008` | disambiguation | other | 0.6 | 0.6 | +0.0 | ✓ |
| `calib-refusal-001` | refusal | glm | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-refusal-002` | refusal | glm | 0.0 | 0.1 | +0.1 | ✓ |
| `calib-refusal-003` | refusal | other | 0.9 | 0.9 | +0.0 | ✓ |
| `calib-refusal-004` | refusal | other | 0.7 | 0.7 | +0.0 | ✓ |
| `calib-refusal-005` | refusal | glm | 0.2 | 0.3 | +0.1 | ✓ |
| `calib-refusal-006` | refusal | other | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-refusal-007` | refusal | glm | 0.9 | 1.0 | +0.1 | ✓ |
| `calib-refusal-008` | refusal | other | 0.1 | 0.1 | +0.0 | ✓ |
| `calib-faithfulness-001` | faithfulness | glm | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-faithfulness-002` | faithfulness | glm | 0.1 | 0.2 | +0.1 | ✓ |
| `calib-faithfulness-003` | faithfulness | other | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-faithfulness-004` | faithfulness | other | 0.0 | 0.0 | +0.0 | ✓ |
| `calib-faithfulness-005` | faithfulness | glm | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-faithfulness-006` | faithfulness | glm | 0.5 | 0.6 | +0.1 | ✗ |
| `calib-faithfulness-007` | faithfulness | other | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-faithfulness-008` | faithfulness | other | 0.6 | 0.6 | +0.0 | ✓ |
| `calib-hallucination-001` | hallucination | glm | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-hallucination-002` | hallucination | glm | 0.4 | 0.5 | +0.1 | ✗ |
| `calib-hallucination-003` | hallucination | other | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-hallucination-004` | hallucination | other | 0.0 | 0.0 | +0.0 | ✓ |
| `calib-hallucination-005` | hallucination | glm | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-hallucination-006` | hallucination | glm | 0.4 | 0.4 | +0.0 | ✓ |
| `calib-hallucination-007` | hallucination | other | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-hallucination-008` | hallucination | other | 0.1 | 0.1 | +0.0 | ✓ |
| `calib-answer-relevancy-001` | answer_relevancy | glm | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-answer-relevancy-002` | answer_relevancy | glm | 0.1 | 0.1 | +0.0 | ✓ |
| `calib-answer-relevancy-003` | answer_relevancy | other | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-answer-relevancy-004` | answer_relevancy | other | 0.4 | 0.4 | +0.0 | ✓ |
| `calib-answer-relevancy-005` | answer_relevancy | glm | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-answer-relevancy-006` | answer_relevancy | glm | 0.2 | 0.3 | +0.1 | ✓ |
| `calib-answer-relevancy-007` | answer_relevancy | other | 0.8 | 0.8 | +0.0 | ✓ |
| `calib-answer-relevancy-008` | answer_relevancy | other | 0.0 | 0.0 | +0.0 | ✓ |
| `calib-context-precision-001` | context_precision | glm | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-context-precision-002` | context_precision | glm | 0.3 | 0.3 | +0.0 | ✓ |
| `calib-context-precision-003` | context_precision | other | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-context-precision-004` | context_precision | other | 0.3 | 0.4 | +0.1 | ✓ |
| `calib-context-precision-005` | context_precision | glm | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-context-precision-006` | context_precision | glm | 0.5 | 0.6 | +0.1 | ✓ |
| `calib-context-precision-007` | context_precision | other | 1.0 | 1.0 | +0.0 | ✓ |
| `calib-context-precision-008` | context_precision | other | 0.0 | 0.1 | +0.1 | ✓ |

---

_Report generated by `scripts/run_calibration.py`._
