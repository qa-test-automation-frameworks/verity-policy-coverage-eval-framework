# A grounded answer can still be stale

**Prevented bad decision:** accepting a grounded but obsolete Silver premium as correct. The source excerpt in `silver.md` says `$420`; the authoritative amendment replaces it with `$445` effective 2024-07-01. A grounding-only pass can therefore reward the wrong current answer.

## Hypothesis and frozen case

For case `defect-2-silver-premium-stale` (golden dataset version `1.0.0`), literal support for an amount is not enough to establish that it is current. The authored negative control says `$420` is current and cites `silver.md`; the authored positive control says the amended premium is `$445` and cites `amendments.md`. Both amounts appear in their selected source files, but only the latter passes the temporal oracle.

The sanitized reproduction report pins SHA-256 identities for the golden input, both corpus files, the temporal-oracle and runner code, and the versioned control configuration: [`temporal-regression-decision.json`](../../reports/case-studies/temporal-regression-decision.json). The oracle's authoritative truth is `$445` (44,500 minor units), with `$420` (42,000 minor units) superseded. The report is generated from the checked-in case and corpus rather than copied from a live model response.

## Results and decision

| Authored output | Literal amount in selected evidence | Temporal result | Control disposition |
|---|---:|---|---|
| “The current Silver plan monthly premium is $420.” | Yes, in `silver.md` | `FAIL` — explicitly claims a superseded amount as current | **Quarantine** |
| “The amended Silver plan monthly premium is $445 effective 2024-07-01.” | Yes, in `amendments.md` | `PASS` | **Ship this authored control** |

The literal check is a narrow grounding illustration, not a semantic faithfulness score. The historic [`semantic/results.json`](../../reports/semantic/results.json) records faithfulness `1.0` against a `0.7` threshold for the stale-premium case, while recording no temporal metric. That is evidence of the grounding/temporal gap; its old run has no complete input, framework, or configuration provenance and is not treated as a measurement of this reproduction. Existing no-key unit controls also cover the bad and good temporal outcomes in [`test_temporal_checks.py`](../../tests/unit/test_temporal_checks.py).

This run contains one purposive case, two authored outputs, zero independent model samples, and zero provider requests. It observed zero execution errors and zero invalid measurements. Token usage and cost are unknown because no provider usage was measured; they are not reported as zero. No production ship decision follows from authored controls. The case decision is to quarantine the stale answer and keep the current-answer control as a positive oracle check.

No Wilson interval is calculated for this one-case demonstration. When applied to repeated sampled measurements, a Wilson interval estimates the probability of crossing a fixed threshold under those sampled conditions; it does not express confidence that the mean score is correct or estimate a production population.

## Reproduce without credentials

From the repository root, run the following commands. The first writes the sanitized two-control artifact linked above; the next commands show each control and how replacing the stale seeded answer reverses its decision.

```sh
uv run python scripts/temporal_decision_case.py --out reports/case-studies/temporal-regression-decision.json
uv run python scripts/temporal_decision_case.py --control stale
uv run python scripts/temporal_decision_case.py --control current
uv run python scripts/temporal_decision_case.py --control stale --answer 'The current Silver plan monthly premium is $445 effective 2024-07-01.' --evidence src/sut/corpus/amendments.md
```

The final command changes the seeded answer and evidence, so the temporal outcome changes from `FAIL`/`quarantine` to `PASS`/`ship`. These controls make no network or provider calls.
