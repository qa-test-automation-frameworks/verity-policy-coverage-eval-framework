# D05 held-out Gemini judge evaluation plan

**Plan ID:** `D05-GEMINI-HELDOUT-2026-10-18-v1`  
**Status:** Frozen design; dataset and reviewer labels not yet assembled  
**Prepared:** 2026-10-18  
**Purpose:** Evaluate agreement between the bounded Gemini judge and two independent human reviewers on a new, held-out set. This plan does not claim that the study ran or that a metric passed.

## Evaluation question and scope

For each of Verity's seven supported calibration metrics, how closely does the configured Gemini judge match two independent reviewers' scores and pass/fail labels on previously unseen, fictional policy-assistant examples?

Target metrics: `answer_relevancy`, `completeness`, `context_precision`, `disambiguation`, `faithfulness`, `hallucination`, and `refusal`. The scope matches the current calibration schema and rubric path; this study will not establish end-to-end validity for the DeepEval/RAGAS adapters, production error rates, or model-family self-preference.

The unit of analysis is one case/metric pair. Prepare **56 cases: 8 per metric**, with 4 intended passes and 4 intended failures per metric. Include every case in the frozen set; do not sample after seeing outputs or exclude cases after scoring begins. Before scoring, only malformed cases or proven tuning-set leakage may be corrected or excluded; document the reason and freeze a new dataset hash first. Use new, fictional policy/source material and new candidate answers, distinct from `datasets/calibration/labeled.yaml`, its cassettes, existing SUT prompts, and any tuning examples. Use distinct scenario families across splits; keep paraphrases or variants from one scenario in one split. Record provenance and a stable family ID in a private key/manifest, and publish only non-sensitive fictional content. Reviewers and the judge see the same frozen case content and metric rubric.

This is an **exploratory calibration**, not a statistically precise production estimate. Eight cases per metric produce coarse rates and wide uncertainty intervals. A metric cannot be promoted based on this study alone if its confidence interval crosses a predeclared bar, the reviewers materially disagree, or sample/data quality is questionable; retain its quarantine and require a larger separately sourced confirmatory set.

## Frozen data and implementation references

The tuning/methodology set is not part of the held-out sample:

| Input | Frozen reference |
|---|---|
| Tuning dataset | `datasets/calibration/labeled.yaml`, 56 cases, 8 each across 7 metrics; SHA-256 `c72cf4dc02065f0e80b7832c645fa25fe7dbf78544d247cb86a156e067f18474` |
| Threshold methodology | `docs/thresholds.md`; SHA-256 `96609f9c70bc9ca28bbff9d8e713100ad4619c7b7801b50c069d45b0394ea708` |
| Scoring implementation | `src/verity/calibration.py`; SHA-256 `b8df779a640ad026bd9f7dba582b504d4f44e72b23177b3b3daa623c59f270d0` |
| Metric rubrics | `src/verity/metrics/rubrics.py`; SHA-256 `d897ed855b08d48eddbad8e1f609793a58add8df744be35cf7ce4c164a5d7d2f` |
| Free-tier runner | `scripts/run_free_hosted_calibration.py`; SHA-256 `8c390d1c3431e56d310e84572bec923ea4985808e8477d24b5d3ef2cf58cb529` |
| Baseline commit | `57068efce2a5d3767ddf81669871abefff6132c5` |
| Judge | Google Gemini API, exact model ID `gemini-3.8-flash`; verify availability and Free-tier eligibility again immediately before any request. No alias or fallback is permitted. |

The held-out dataset is not yet created; its version, SHA-256, source-family counts, construction timestamp, leakage review, and deterministic case-selection rule must be added to a v2 plan amendment **before any held-out judge score is requested**. If any rubric, scoring prompt, threshold, model, or inclusion rule changes after scores are requested, retire this split from confirmatory use and prepare a new holdout. Preserve the original v1 plan and results.

## Review and blinding

Obtain two reviewers who did not author the held-out cases, candidate outputs, scoring rubrics, or labels. The owner may serve as one reviewer only if those independence conditions are met; recruiting a second reviewer is in progress. Record pseudonyms and role/independence attestations, not personal contact details, in the repository.

Each reviewer independently scores every case on the existing normalized 0–1 scale, selects pass/fail using the frozen 0.5 score boundary used by the current calibration implementation, records confidence and a concise rationale, and submits a completed copy of `docs/independent-calibration-labels.template.csv`. Give reviewers randomized case IDs, metric rubric, required source context, and candidate output. Do not show judge score/explanation, synthetic/reference labels, output-family/provider/model, prompt version, split membership, or the other reviewer's responses. Keep the randomized-ID mapping separate until both label files are locked and SHA-256 hashed.

Compute judge agreement separately against each reviewer's locked labels; do not silently replace either reviewer's labels with a consensus. Report reviewer-to-reviewer agreement as well. If a third-person adjudication is needed, preserve original labels and report adjudication only as secondary analysis. No labels are present in this plan.

## Analysis and decision rules

For each metric and each reviewer, report `n`, raw binary pass/fail agreement, Cohen's kappa when the label distribution makes it meaningful, and 0–1 score MAE. Report the same measures for all cases only as secondary summaries; the aggregate cannot hide a failing metric. Report the two reviewers' agreement and missing/invalid judgments.

Freeze these decision bars before data collection, applying them per metric and per reviewer comparison:

- Raw agreement at least **85%**.
- Score MAE no greater than **0.20**.
- Cohen's kappa at least **0.60** where non-degenerate marginals make it meaningful; otherwise label kappa not interpretable and do not substitute a more favorable statistic post hoc.
- Report two-sided 95% Wilson intervals for binary agreement and a case-resampled percentile 95% bootstrap interval for MAE (10,000 resamples; deterministic seed `20261018`; resample within metric). These intervals are descriptive at this small sample size. If an interval includes a decision boundary, treat the metric result as inconclusive and keep it quarantined.

Do not retune, omit cases, reclassify failures, or change thresholds after unblinding. Record all protocol deviations and provider failures. A free-tier outage or quota response is a failed/incomplete attempt, not a score; stop without retries or fallback, retain earlier attempts, and resume only as a separately logged continuation under this same frozen plan. No incomplete output is imputed.

## Hosted execution and zero-spend boundary

The user requires hosted AI only and zero authorized spend. The user previously attested that the key's Google AI Studio project is Free tier with billing disabled; recheck that exact project/key before execution. Do not enable billing, use a paid project/key, or accept a paid fallback. Google documents that Gemini free-tier availability varies by model and that free-tier data may be used to improve products; use only fictional, public repository-created examples. The selected model's pricing and availability must be rechecked on the execution date ([pricing](https://ai.google.dev/gemini-api/docs/pricing), [billing and Free tier](https://ai.google.dev/gemini-api/docs/billing)).

Use `scripts/run_free_hosted_calibration.py` with its explicit free-project confirmation. The runner's current bounds are seven requests per invocation, 2,048 output tokens per request, 14,336 output tokens per invocation, 16,000 input UTF-8 bytes per request, 45-second timeout, at least 3.1 seconds between requests, and zero SDK retries/fallback. A complete 56-case judge evaluation therefore requires at least eight bounded invocations; split only at predeclared case boundaries and preserve every receipt. Stop at the first quota/auth/outage/invalid-output/cost anomaly. Do not infer that a free account guarantees availability or a particular quota.

Before each invocation, verify account Free status and disabled billing. Record operator attestation, UTC time, source commit, dataset and prompt hashes, model ID, per-invocation limits, call/token/latency counts, provider response IDs, failures, and artifact checksums. `provider_reported_cost_usd: null` means unreported, not measured zero. No credentials may appear in commands, logs, repository artifacts, or reviewer files.

## Artifacts and completion boundary

Expected artifacts, created only after the plan and held-out dataset are frozen:

1. A held-out dataset plus provenance/family manifest and SHA-256, with no reviewer labels or judge scores embedded in the blinded reviewer copy.
2. Two independently completed CSV label files, locked and hashed before unblinding, plus pseudonymous independence attestations.
3. Bounded live Gemini receipts and an immutable evidence index with all eight-or-more invocation outcomes, including failures.
4. Reproducible analysis output containing per-metric/per-reviewer measures, uncertainty intervals, disagreements, missing data, deviations, an explicit retain-quarantine/promote recommendation, exact input hashes, analysis-tool hashes, and the analysis commit.

Run the offline analyzer only after both reviewer files are locked and the judge run is complete; it checks the dataset hash against the private mapping manifest, exact randomized-ID/metric alignment, case balance, separate labels, and the fixed score/pass boundary before emitting aggregate JSON:

```bash
PYTHONPATH=src:. uv run python scripts/analyze_d05_heldout.py \
  --reviewer-one /private/path/reviewer-one.csv \
  --reviewer-two /private/path/reviewer-two.csv \
  --judge-scores /private/path/judge-scores.csv \
  --heldout-dataset datasets/calibration/heldout-d05.yaml \
  --case-manifest /private/path/heldout-manifest.json \
  --output reports/calibration/d05-heldout-analysis.json
```

Keep the manifest outside each reviewer's view until both label files are locked; the report contains hashes, not source-ID mappings or reviewer rationales.

D05 remains incomplete until independent labels are collected and locked, the planned live calls and receipts are reconciled, analysis is independently reviewed, and any security findings blocking PR #32 are resolved through reviewed dependency disposition. This document and the corrected tuning-set header are preparation only.
