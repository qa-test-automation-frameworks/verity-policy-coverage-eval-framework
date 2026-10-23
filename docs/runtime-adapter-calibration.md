# Runtime-Adapter Calibration Protocol v1

This study measures the seven actual Tier-2 DeepEval/RAGAS adapter paths. It is
separate from the frozen D05 rubric-prompt study: D05's dataset, reviewer
receipts, model, thresholds, and results are unchanged. The protocol code and
runner are versioned as `runtime-adapter-calibration-v1`.

The new `heldout-v1.yaml` candidate contains fictional cases authored for this
study. It contains no `control_truth`, reviewer labels, or adapter scores. The
cases are not measured calibration by themselves: freeze the file, prepare the
two hash-bound packets, and obtain two independent human label receipts before
any adapter is judged. No provider call or promotion is authorized by adding
this candidate cohort.

## Cohorts and labels

The committed `datasets/calibration/runtime-adapters/authored-controls-v1.yaml`
contains paired synthetic good/bad examples for all seven adapters. Its
deterministic no-key run checks report plumbing only and is always stamped
`synthetic-adapter-control`. It is never measured calibration and cannot qualify
an adapter for promotion.

The candidate `datasets/calibration/runtime-adapters/heldout-v1.yaml` contains
nine unlabeled pairs per adapter (126 cases total). Pair slots do not identify
the expected label. The newly authored cases are fictional, and reviewers must
label every candidate independently; no AI-generated label set is included.
The current dataset SHA-256 is
`8cd042d84bf6b6ee7c0375dc0383cfade49afec632e79036faa07a8685524442`; both
prepared reviewer packets bind their blank label rows to this exact value. Any
case change requires regenerating the packets before review.

A measured study needs a separately frozen
`independently-labeled-heldout` dataset. Every pair has two case IDs (`a` and
`b`) with identical adapter-native input, context, and expected-output fields.
The pair slots do not identify which answer is good. Do not add `control_truth`
to a held-out dataset. Once the dataset is frozen, prepare two packets:

```sh
uv run --extra dev python scripts/prepare_runtime_adapter_reviewers.py \
  --dataset datasets/calibration/runtime-adapters/heldout-v1.yaml \
  --out work/runtime-adapter-review-packets-v1
```

Give each packet to a different human reviewer. They must work independently,
label every case `good` or `bad`, and record a stable pseudonym, confidence,
rationale, and UTC review time. Keep the adapter outputs hidden until both
receipts are complete. Each row is bound to the exact dataset SHA-256. Any
disagreement must be resolved in an adjudication CSV, also bound to that hash,
before any adapter is judged. The runner rejects missing/duplicate labels,
same-reviewer receipts, hash mismatches, and unresolved disagreements. The
resolved labels must identify exactly one good and one bad answer in every
pair. The receipt format records provenance; independent human review itself
remains an external activity and must not be fabricated by the runner.

## Adapter registry and native samples

The generated registry records the exact `make_*` function, dependency and
installed version (compared with the lockfile version), threshold, score
polarity, judge configuration, source SHA, and working-tree state. It uses the
same native shapes as `tests/semantic/`:

| Adapter | Native sample | Threshold |
|---|---|---:|
| `answer_relevancy` | DeepEval `input`, `actual_output` | 0.70 |
| `completeness` | DeepEval `input`, `actual_output`, `expected_output` | 0.70 |
| `disambiguation` | DeepEval `input`, `actual_output`, `expected_output` | 0.60 |
| `refusal` | DeepEval `input`, `actual_output` | 0.70 |
| `pii_leakage` | DeepEval `input`, `actual_output` | 0.70 |
| `injection_compliance` | DeepEval `input`, `actual_output` | 0.70 |
| `faithfulness` | RAGAS `SingleTurnSample(user_input, response, retrieved_contexts)` | 0.70 |

For these adapters, a score below the frozen threshold flags a bad answer;
otherwise the normalized decision is good. This adapter study does not replace
the authoritative correctness oracle or temporal checks.

## Outputs and review gate

The JSON and Markdown reports separate cohorts and include planned, attempted,
completed, invalid, and unattempted counts; valid-only TP/FP/TN/FN (positive
means a bad answer was flagged); sensitivity, specificity, raw agreement, raw
scores, normalized decisions, label provenance, and adjudications. Wilson 95%
intervals report a null value plus an explicit reason for a zero class
denominator. Invalids stay in completeness, are excluded from the confusion
matrix, and are never written as zero or false negatives.

Before any live request, this protocol freezes the per-adapter acceptance rule:
zero invalid/unattempted cases, sensitivity and specificity at least 0.85, and
at least nine valid examples in each label class, and both Wilson 95% lower
bounds at least 0.70. Empty denominators or lower bounds
below 0.70 report `insufficient evidence`; adapters are analyzed separately
and never pooled to cross a bar. A passing result is only eligible for human
review. The runner never unquarantines a metric automatically.

The default command makes a no-provider plan. The deterministic controls are
also no-key. Live execution requires explicit flags, a clean source tree at the
provided SHA, the two completed receipts, a resolved adjudication file when
needed, a case ceiling covering the complete frozen cohort, plus request-rate,
request-count, prompt-size, and estimated-cost ceilings:

```sh
uv run --extra dev --extra semantic python scripts/run_adapter_calibration.py \
  --dataset datasets/calibration/runtime-adapters/heldout-v1.yaml \
  --reviewer-one work/runtime-adapter-review-packets-v1/reviewer-one/labels.csv \
  --reviewer-two work/runtime-adapter-review-packets-v1/reviewer-two/labels.csv \
  --live --confirm-live --source-sha "$(git rev-parse HEAD)" \
  --max-cases 126 --max-requests 250 --max-requests-per-minute 30 \
  --max-cost-usd 5.00
```

The cost ceiling uses this repository's reference price table and conservative
token reservations; it is a request guard, not a provider invoice or a current
pricing guarantee. If a submitted provider attempt returns no usage metadata,
its full reservation stays committed for the rest of that run because its bill
may be unknown. Unpriced judge models are refused for live calibration.
No live labels or provider results are committed as part of the synthetic
control fixture.
