# A paired comparison needs an oracle and a fixed cohort

The offline analyzer accepts one JSONL measurement per `(case_id, candidate_id)`. It pairs only records with the same input hash, oracle version, cohort hash, and source kind. Duplicate IDs, one-sided cases, and identity mismatches produce explicit diagnostics and make the result inconclusive instead of disappearing in an inner join.

The [temporal-regression fixtures](../../datasets/comparisons/temporal-regression/) are authored controls, not model runs. They show the stale answer failing and the amended answer passing for the same input. The denominator is one independent case, so the policy correctly returns `inconclusive` below its minimum of 30. Token usage, latency, and cost are unknown; authored controls cannot support cost-savings claims.

Reproduce without credentials from the repository root:

```sh
uv run python scripts/analyze_model_comparison.py \
  --baseline datasets/comparisons/temporal-regression/baseline.jsonl \
  --challenger datasets/comparisons/temporal-regression/challenger.jsonl \
  --out /tmp/paired-model-comparison.md
```

The command writes a one-page Markdown summary and a JSON report beside it. The JSON includes every case's input/oracle identity, candidate config/source IDs, paired outcomes and cost/latency deltas, denominators, exclusions, and bootstrap parameters.

The quality-only policy predeclares a 0.02 non-inferiority margin and uses 2,000 case-level bootstrap resamples with seed `20261021`. A challenger critical failure rejects first; invalid or incomplete measurements and fewer than 30 independent valid cases are inconclusive. Cost savings are supported only with complete actual measured live/replay costs; cost alone cannot override a correctness failure. The analysis never deploys a candidate.

Each candidate must aggregate repeated runs within a case before writing the one-row-per-case contract; duplicate case IDs are rejected so repeats cannot inflate the independent-case denominator. For imported records, set `cost_usd` to `null` unless it is the actual billed amount for that call. A zero is valid only when the recorded charge was actually zero. Price-table estimates, cached estimates, and authored fixture amounts are not measured cost and must not be supplied as evidence. The analyzer relies on that input contract; the optional live export leaves cost unknown because `RunAccumulator` reports estimates rather than billing.
