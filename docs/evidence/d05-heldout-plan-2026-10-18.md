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
| Scoring implementation | `src/verity/calibration.py`; SHA-256 `b369a312da70657dcf935c331dbf407d7ba34ae48d4218dde804a1251a297d8d` |
| Metric rubrics | `src/verity/metrics/rubrics.py`; SHA-256 `d897ed855b08d48eddbad8e1f609793a58add8df744be35cf7ce4c164a5d7d2f` |
| Free-tier runner | `scripts/run_free_hosted_calibration.py`; SHA-256 `1dd3637bfa60e632fe4a138713750558a27d09811315eb081bbba6fa842148f9` |
| Frozen scoring/runner commit | `20b177d57f1b0ab4c31bdbe5f29cc1bc0554deb1`; no held-out scores have been requested. |
| Judge | Google Gemini API, exact model ID `gemini-3.8-flash`; verify availability and Free-tier eligibility again immediately before any request. No alias or fallback is permitted. |

The held-out dataset is not yet created; its version, SHA-256, source-family counts, construction timestamp, leakage review, and deterministic case-selection rule must be added to a v2 plan amendment **before any held-out judge score is requested**. If any rubric, scoring prompt, threshold, model, or inclusion rule changes after scores are requested, retire this split from confirmatory use and prepare a new holdout. Preserve the original v1 plan and results.

## Review and blinding

Obtain two reviewers who did not author the held-out cases, candidate outputs, scoring rubrics, or labels. The owner may serve as one reviewer only if those independence conditions are met; recruiting a second reviewer is in progress. Record pseudonyms and role/independence attestations, not personal contact details, in the repository.

Each reviewer independently scores every case on the existing normalized 0–1 scale, selects pass/fail using the frozen 0.5 score boundary used by the current calibration implementation, records confidence and a concise rationale, and submits a completed copy of `docs/independent-calibration-labels.template.csv`. Give reviewers randomized case IDs, metric rubric, required source context, and candidate output. Do not show judge score/explanation, synthetic/reference labels, output-family/provider/model, prompt version, split membership, or the other reviewer's responses. Keep the randomized-ID mapping separate until both label files are locked and SHA-256 hashed.

Generate two non-overwritable blank forms directly from the frozen dataset; the command reads no private manifest and includes no expected labels:

```bash
PYTHONPATH=src:. uv run python scripts/prepare_d05_reviewer_packets.py \
  --out-dir /private/path/d05-review-forms-v3
```

Provide each CSV to a different qualified reviewer along with the frozen dataset and metric rubrics. Give both the same materials independently; do not expose either completed form, the private manifest, or any judge receipt/score before both forms have been returned and locked.

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

Use `scripts/run_free_hosted_calibration.py` in explicit held-out mode with its free-project confirmation; do not use the tuning smoke for study scores. Example for the first batch (repeat with `--start-index 7`, `14`, `21`, `28`, `35`, `42`, and `49`):

```bash
PYTHONPATH=src:. uv run python scripts/run_free_hosted_calibration.py \
  --live --confirm-free-project --heldout-study \
  --heldout-dataset datasets/calibration/heldout-d05.yaml \
  --start-index 0 --max-calls 7 \
  --out reports/free-hosted/heldout-d05
```

The runner's bounds are seven requests per invocation, 2,048 output tokens per request, 14,336 output tokens per invocation, 16,000 input UTF-8 bytes per request, 45-second timeout, at least 3.1 seconds between requests, and zero SDK retries/fallback. A complete 56-case judge evaluation therefore requires at least eight bounded invocations; split only at the predeclared contiguous case boundaries and preserve every receipt. Stop at the first quota/auth/outage/invalid-output/cost anomaly. Do not infer that a free account guarantees availability or a particular quota.

After all eight-or-more batches, reconcile raw receipts before analysis. This emits the immutable run index even when the study is incomplete; it writes the score CSV only if each frozen case has exactly one successful score and all receipt/model/dataset/free-tier checks pass. Failed attempts remain in the index and are never imputed:

```bash
PYTHONPATH=src:. uv run python scripts/export_d05_heldout_scores.py \
  --heldout-dataset datasets/calibration/heldout-d05.yaml \
  --receipt-dir reports/free-hosted/heldout-d05 \
  --scores-out reports/calibration/d05-heldout-judge-scores.csv \
  --index-out reports/calibration/d05-heldout-run-index.json
```

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

## Additive v2 amendment — held-out dataset frozen before any scoring

Amended `2026-10-18T04:17:57Z`, before any held-out Gemini score was requested. Preserve the v1 protocol and fingerprints above. This amendment freezes the dataset identity and records construction checks; it does not add labels or change the scoring rubric, prompt, model, threshold, decision bars, or inclusion rules.

| Dataset record | Frozen value |
|---|---|
| Dataset | `datasets/calibration/heldout-d05.yaml` |
| SHA-256 | `8922644746357492f20bba794ba198d6210fab7ec5381feece224961bc11b77f` |
| Cases | 56 total; 8 per each of the 7 frozen metrics; randomized row order and opaque case IDs |
| Source families | 56 distinct fictional source families; no case-family variants are reused across this split |
| Design balance | Four intended passing and four intended failing examples per metric; this is authoring intent only, not a reviewer label or judge result |
| Private mapping manifest | Local `work/d05-heldout-analysis/private-manifest.json`; SHA-256 `7a862c35924bdda20bf2cbd838dec971f12750d058a1a03b82dee868994eb34d` |
| Tuning-set overlap check | No exact normalized query/candidate-response pair overlaps `datasets/calibration/labeled.yaml`; the new examples use fictional plan names and distinct case families |

The manifest maps randomized IDs to source-case and source-family IDs and must remain outside reviewers' view until both label files are locked. It contains no reference labels. The blinded YAML contains no scores, pass labels, explanations, or expected answers. Schema loading and manifest/hash validation passed locally; the metric counts and unique-family count were checked before freezing. Reviewers must score the frozen text as provided and must not use any private authoring notes. A substantive dataset correction now requires a further dated additive amendment, new dataset/manifest hashes, and a fresh freeze before either human labels or judge scoring are collected.

Current execution state after this amendment: no reviewer label files exist; no held-out Gemini scores or provider calls exist; no outcome is claimed. Both independent reviews must be locked and hashed before any score exposure/unblinding. Continue the existing zero-spend, stop-on-first-failure protocol.

## Additive v3 amendment — correct one out-of-scope refusal prompt

Amended `2026-10-18T04:18:40Z`, before any held-out Gemini score was requested or any reviewer labels were collected. During a rubric-fit audit, one case in the refusal metric asked whether physical therapy was covered, which is an in-scope benefit question and therefore not a valid refusal challenge. Changed only that query to ask whether physical therapy or medication is the best treatment for lower-back pain, preserving the deliberately unsafe candidate response and the case's randomized ID/source family. This corrects scope alignment; it does not change any frozen rubric, score boundary, threshold, metric allocation, or decision bar.

| Dataset version | SHA-256 | Status |
|---|---|---|
| v2 | `8922644746357492f20bba794ba198d6210fab7ec5381feece224961bc11b77f` | Superseded before labels/scoring; retained in the preceding Git commit |
| v3 | `e4b64cb91ecf0921d4a5ca13f2cf6606bf39c3a95f92254282135a82585f4e21` | Current frozen dataset |

Updated private mapping manifest remains at local `work/d05-heldout-analysis/private-manifest.json`, now SHA-256 `d3bfe568fdd79bdc54bcdb6ea8459e635c24f618073b9a47410204d4832ef5a1`. It contains no label or expected-result field. The seven-by-eight balance and 56 unique source families remain unchanged. Re-run schema, manifest, prompt-size and tuning-overlap validations against v3 before reviewer distribution; only this v3 hash may be used for labels or scoring.

## Additive v4 amendment — bounded free-tier availability attempts

Amended `2026-10-18T04:30:32Z`; dataset v3, rubric, prompt, model, threshold and decision bars are unchanged. Google's authenticated model catalogue preflight for `gemini-3.8-flash` succeeded with `generateContent` support and no inference request. The owner had confirmed the key's project is Free tier with billing disabled; the runner made two separately receipted, bounded live study invocations against the v3 dataset and stopped on each first failed request, with no retries or fallback:

| Receipt (local private evidence) | Invocation | First request outcome | SHA-256 |
|---|---|---|---|
| `work/d05-heldout-analysis/heldout-v3/heldout-1792297645094763993.json` | initial batch, start index 0, limit 7 calls | HTTP 408 / `Timeout`; no score | `91c55cbaab56ebecfe253ed31773ed51b8baf8e1f6110832005697dc305eea13` |
| `work/d05-heldout-analysis/heldout-v3/heldout-1792297807071986153.json` | separately logged continuation, start index 0, limit 7 calls | HTTP 503 / `ServiceUnavailableError`; no score | `fbecdbf60fcc09c619ee593c5d928db3618d11db977d4a7d638a3c4ead5301eb` |

The frozen receipt exporter reconciled both receipts as incomplete: 0 of 56 successful scores, all 56 cases missing, and no judge-score CSV emitted. The private index is `work/d05-heldout-analysis/d05-heldout-run-index.json`, SHA-256 `d7c07a247c3b6f7bd27c78db8e1208b50fd09b7f8a146044cf466128401c924e`. No provider-reported cost field was returned for either failed request; exact usage/cost is therefore unreported. No paid fallback or billing activation occurred. Stop further calls for this session; only a later, separately logged continuation under this same plan may proceed after provider availability is rechecked. Do not expose any judge score before both independent label files are locked. No reviewer labels have been collected, so there is no calibration result or threshold disposition.

## Additive v5 amendment — align Gemini 3 generation settings

Amended `2026-10-18T04:34:03Z`, before any valid score exists. The v4 attempts remain failed transport attempts (HTTP 408 and 503) and cannot contribute scores. Google's current Gemini 3 guidance recommends the default temperature of `1.0`; lower values may degrade behavior. The updated runner therefore freezes `temperature: 1.0` and `reasoning_effort: low`, which the repository's pinned LiteLLM Gemini adapter maps to Gemini `thinkingConfig.thinkingLevel: low`. The integration test verifies this exact request body, including LiteLLM's required `allowed_openai_params` pass-through.

This is a generation-configuration amendment only. The v3 dataset and its SHA-256, rubric, scoring prompt, model ID, case boundaries, thresholds, review protocol, limits, and zero-retry/no-fallback rules are unchanged. The receipt reconciler rejects any successful score without the amended generation configuration; earlier failed receipts remain valid failure records. Exact source fingerprints for the runner and provider adapter are recorded in the implementation commit and verification log. No hosted inference request was made while making or validating this amendment. Do not continue provider calls during the current session; a later continuation must recheck free-project/billing state and model availability and be separately recorded.
