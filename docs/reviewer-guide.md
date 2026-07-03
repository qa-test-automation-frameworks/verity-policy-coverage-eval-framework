# Reviewer Guide

A path through this repo for someone evaluating it as a portfolio artifact, at three depths.

## 10 minutes: does it run and is it honest?

```bash
git clone <repo-url> && cd verity-policy-coverage-eval-framework
uv sync --all-extras
PYTHONPATH=src uv run pytest tests/unit -q -p no:cacheprovider
```

Expect all of them to pass in well under a minute, no API key required — the exact count
drifts as cases are added, so treat "all green" as the signal, not a specific number. Then
read, in order:

1. `README.md` — "What This Proves" and "Limitations" sections. Limitations are stated
   plainly, not buried; that's the thing to notice.
2. `docs/defects-caught.md` — the seeded-defect matrix. Note the "Evidence Type" column:
   `authored-cassette detector replay` proves the detector fires, `live semantic run` means a
   real model/judge call happened. `NOT_REPRODUCED` is a distinct status from
   `CAUGHT`/`VERIFIED`, not folded into "pass".
3. `docs/adr/0001-glm-4-5-model-choice.md` — two amendments at the bottom: the first names the
   gap between the originally advertised default provider and the one actually validated live;
   the second records that the default was later switched to match the validated pairing.
4. `docs/known-issues.md` — KI-3: control-case gating on faithfulness and answer relevancy is
   currently quarantined (`@pytest.mark.quarantine`), not silently passing or silently removed.
5. `README.md` — "Current Gate Status" names which checks are enforced, informational, or
   quarantined before you run anything live.

## 30 minutes: does the evaluation machinery hold up?

Add to the above:

- `tests/semantic/conftest.py` — `record_defect_measurement` marks the test `xfail` when a
  seeded defect isn't reproduced (search for `pytest.xfail`), keeping the tier's pass/fail
  signal reserved for detector errors and control-case regressions; it does not just log a
  metric and pretend the run was green.
- `scripts/defects_report.py` — `_PASS_STATUSES` and how `NOT_REPRODUCED` is classified.
- `src/verity/statistics.py` and `docs/adr/0005-statistical-thresholds.md` — how N-sample
  aggregation and threshold_pass work, and why N differs between local/push and scheduled runs.
- `src/verity/checks.py`'s `check_citations` — validates citations at the source-file level
  always, and at the exact (source, section) level when a caller passes `retrieved_chunks`
  (`tests/deterministic/test_response_schema.py` does). `check_claim_numbers_grounded`
  covers numeric claims, and `check_policy_claims_grounded` adds deterministic lexical
  support checks for material qualitative policy statements. These checks still do not prove
  full entailment, but they catch unsupported claims that a source-only citation check misses.
- Run `make test-deterministic` and `make defects-report` locally (both hermetic, no API key).

## Deep review: everything

- `docs/architecture.md` for the framework/SUT split and data flow.
- `docs/adr/` for every architectural decision and its alternatives-considered table.
- `docs/thresholds.md` and `docs/calibration-report.md` for how each metric's pass/fail
  threshold was chosen and how well it agrees with human labels.
- `docs/dataset-coverage.md` for the golden-case breakdown by plan tier, risk weight,
  expectation category, and seeded-defect linkage — regenerate with `make dataset-matrix`.
- `docs/owasp-llm-coverage.md` for how the adversarial probe corpus maps to the OWASP Top 10
  for LLM Applications, including what's explicitly out of scope and why.
- `docs/retrieval-ablation.md` for measured evidence behind the retriever's hand-tuned
  constants (`_LEXICAL_WEIGHT`, `_DISTANCE_MARGIN`, `_MAX_RELEVANT_DISTANCE`) rather than
  taking the "hand-tuned starting point" code comments on faith.
- `datasets/golden/*.yaml` and `datasets/adversarial/probes.yaml` for the actual test
  data — read a handful of cases end to end rather than trusting the summary counts.
- `src/sut/agent.py` for the orchestration path (auth/guardrails/retrieval/tool-calls/
  citations/review-flagging split across `answer()` and `_prepare_request()` — a known
  complexity area, not hidden).
- `.github/workflows/` for what's a required PR gate vs. a scheduled/informational job.
- `docs/future-work.md` for what this repository has deliberately not done yet, and exactly
  what command would close each gap.

## What to look for that would be a red flag

- A claim in `README.md` that isn't backed by a linked report or a runnable command.
- A status table (`docs/defects-caught.md`, `docs/calibration-report.md`) whose summary row
  doesn't match its own detail rows.
- A threshold or default that's stated in one doc and contradicted by the actual code
  (`src/verity/config.py`, `.env.example`, the relevant workflow YAML).
