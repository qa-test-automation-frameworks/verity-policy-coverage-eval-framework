# ADR-0005: Distribution-over-N Statistical Thresholds

**Status:** Accepted

## Context

LLM outputs are non-deterministic even at `temperature=0`: floating-point
arithmetic, batching effects, and provider-side sampling can produce slightly
different scores on repeated calls with identical inputs. A single-run metric
threshold of the form `assert score >= 0.7` will flake: the same code may pass
one run and fail the next by a margin of 0.02-0.05.

Flaky tests erode trust in the CI suite faster than bugs do. A test that
intermittently fails for no reproducible reason is eventually disabled.

## Decision

Replace single-run brittle assertions with **distribution-over-N statistical
thresholds** implemented in `verity/statistics.py`:

- `run_n_samples(fn, n)`: calls `fn()` (a metric scoring function) N times and
  collects the scores. Default N=3 for the Tier-2 suite (balances cost vs.
  statistical confidence; configurable per metric).
- `aggregate(scores)`: computes mean, median, standard deviation, and pass_rate
  (fraction of runs where score >= threshold).
- `threshold_pass(stat, threshold, mode)`: evaluates the aggregated stat against
  a threshold using one of three modes:
  - `mean` — `stat.mean >= threshold` (default; smooths one-off outliers)
  - `median` — more robust to a single very-low outlier
  - `pass_rate` — `stat.pass_rate >= required_fraction` (useful when any single
    failure is acceptable but consistent failure is not)

Thresholds are set per metric and documented in `docs/thresholds.md` with
explicit rationale for each value and the defect coverage it provides.

### Example

```python
stat = aggregate(run_n_samples(lambda: score_faithfulness(case), n=3))
assert threshold_pass(stat, THRESHOLD_FAITHFULNESS, mode="mean"), (
    f"Faithfulness below threshold: mean={stat.mean:.3f}, "
    f"threshold={THRESHOLD_FAITHFULNESS}, scores={stat.scores}"
)
```

## Consequences

**Easier:**
- A single genuinely flaky run (score 0.65 against a threshold of 0.70) will not
  cause a test failure if the mean of 3 runs is 0.74.
- The mean and individual scores are printed on failure, making it easy to
  distinguish a real regression from random variance.
- The statistical approach is a teachable, reproducible competency demonstration.

**Harder:**
- N=3 runs of the semantic suite makes each test 3x more expensive and 3x slower.
  This is acceptable because Tier-2 runs nightly, not on every PR.
- Setting the right threshold requires initial calibration runs. Too high =
  false failures; too low = misses real regressions. See `docs/thresholds.md`.

## Alternatives Considered

| Alternative | Rejected because |
|-------------|-----------------|
| Single-run with loose threshold | Does not catch genuine regressions; invites threshold-gaming |
| `pytest-rerunfailures` retry | Retries mask flakiness instead of modelling it statistically |
| Fixed random seed | LLM providers do not expose or guarantee a usable inference seed |
| Property-based testing (Hypothesis) | Does not map naturally to LLM metric scoring |

## Amendment (2026-07-02): default N lowered from 3 to 1 for local/push runs

The original default of N=3 for every Tier-2 run was never adopted in
practice: `VERITY_SEMANTIC_SAMPLES` defaults to `1` (`.env.example`,
`Settings.semantic_samples` in `verity/config.py`) for local runs and pushes
to `main`, and `.github/workflows/semantic-eval.yml` explicitly sets `N=5`
for the nightly scheduled run instead of the ADR's N=3. The reasoning above
for why N>1 matters is unchanged, but N=3 was cost/latency-prohibitive to
run on every push once the golden dataset grew past its original size.

Current behavior: N=1 on local runs and pushes (cheap, catches gross
regressions immediately; the mean/median/pass_rate machinery in
`verity/statistics.py` degenerates to a single-sample read at N=1), N=5 on
the nightly schedule (the run that actually exercises the distribution-over-N
statistics this ADR describes). See `docs/thresholds.md` for the current
per-metric N and threshold values.
