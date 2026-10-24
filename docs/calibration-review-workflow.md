# Independent held-out calibration review

This protocol prepares an independent evaluation of the Verity semantic judge.
It does not report human labels, live provider results, or threshold promotion.
The runtime DeepEval/RAGAS adapter protocol is separate and is documented in
[Runtime-Adapter Calibration Protocol v1](runtime-adapter-calibration.md); do
not treat held-out rubric scores as runtime-adapter measurements.
The current `datasets/calibration/labeled.yaml` is a tuning/methodology set: its
labels are synthetic and its replay cassettes are authored. Do not select those
cases as the held-out evaluation set or describe their results as independent
human calibration.

For the owner's hosted-only, zero-spend constraint, use the
[free hosted route guide](free-hosted-calibration.md) to check availability and
exercise a bounded tuning-set smoke. That smoke does not replace this protocol.

## 1. Freeze the evaluation plan

Before generating any held-out judge scores, commit a plan that records:

- the evaluation question, target metrics, score scale, pass thresholds and
  promotion rule;
- the tuning dataset version and SHA-256, plus the held-out dataset version and
  SHA-256 once it has been assembled;
- case inclusion/exclusion rules, source-family grouping, metric balance,
  sample-size rationale and the analysis method;
- the SUT, judge, provider, model identifiers, prompt/rubric revisions and
  runtime versions; verify that the provider supports the chosen identifiers on
  the execution date;
- explicit per-run call, token and spend caps, timeout/retry limits, and the
  failure behavior when a cap or provider limit is reached.

Keep all paraphrases, variants, and outputs derived from one source scenario in
the same split. Do not use held-out results to tune prompts or thresholds and
then report those same results as independent validation. If tuning changes
after the first held-out run, retire that split from confirmatory use and prepare
a newly sourced holdout.

## 2. Prepare a genuinely held-out set

Use cases that were not used to author, tune, or replay the current rubrics and
thresholds. Track source provenance and a stable source-family identifier so
near-duplicates cannot cross the tuning/holdout boundary. Record the dataset
hash, case count by metric and family, construction date, and leakage review.
Exclude personal or confidential data unless its use has been explicitly
authorized and its handling is documented.

Predeclare the sample size and report uncertainty at the metric level. A small
sample is suitable only for an exploratory result; it must not be presented as
precise evidence of production error rates. Use a fixed, documented confidence
interval method and preserve the random seed or deterministic selection rule.

## 3. Blind independent reviewers

Recruit at least two reviewers who did not author the cases, candidate answers,
rubrics, or current labels. The repository owner is responsible for obtaining
their agreement and any required approvals; this protocol does not imply that
review has occurred.

Give each reviewer a randomized case identifier, the policy/rubric needed for
that metric, the source context, and the candidate output. Do not show the
judge's score or explanation, existing synthetic/reference label, model family,
provider, prompt version, other reviewers' answers, or tuning/holdout status.
Keep the key that maps randomized IDs to source IDs outside each reviewer's
labeling view until labels are locked.

Each reviewer records an independent score on the declared scale, a pass/fail
label derived from the frozen threshold, confidence, and a short rationale.
Store a pseudonymous reviewer ID; do not put personal contact details in the
repository. Lock and hash each completed reviewer file before unblinding or
adjudication.

## 4. Capture disagreements and provenance

Use [`independent-calibration-labels.template.csv`](independent-calibration-labels.template.csv)
as a blank header template. Store completed labels separately from the template
and include the plan ID, held-out dataset hash, reviewer-file hashes, case
selection seed/rule, and adjudication record. Preserve original independent
labels even when a third reviewer adjudicates a disagreement; never overwrite
them with a consensus label.

Record the actual live run ID, UTC start/end, source commit, provider/model
identifiers, prompt/rubric hashes, call/token counts, measured cost, latency,
retries, failures and artifact checksums. Keep replay-detector results in a
separate section from live judge results. Preserve `NOT_REPRODUCED` and control
failures; do not turn them into passes during analysis.

## 5. Analyze and decide without post-hoc tuning

Report case counts and missing/invalid outputs, raw agreement, a chance-adjusted
agreement statistic where its assumptions fit, score error (including MAE),
confusion by metric and model family where applicable, and uncertainty
intervals. Explain metric imbalance, reviewer disagreement, adjudication, cost,
latency, provider errors and all deviations from the frozen plan. Do not
aggregate away a failing metric behind a portfolio-wide mean.

Use the predeclared thresholds. The current methodology bar in
[`thresholds.md`](thresholds.md) is at least 85% agreement and MAE no greater
than 0.20; the historical kappa bar is at least 0.60 where kappa is meaningful
for the label distribution. Report all bars and intervals rather than changing
them after seeing results. A metric that misses its bar remains quarantined.
Promote a quarantined metric only after the held-out live evidence satisfies
the predeclared criteria and the review is independently accepted; otherwise
retain the quarantine with its owner role, review date, expiry, and next action.

## 6. Completion boundary

The protocol and blank template are preparation only. The held-out study remains incomplete
until the owner authorizes bounded live execution, independent labels are
collected and locked, the actual artifacts are reconciled, and the held-out
analysis supports a defensible conclusion. No provider price, reviewer
agreement, human label, or live result is assumed by this document.
