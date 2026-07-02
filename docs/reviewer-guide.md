# Reviewer Guide

A path through this repo for someone evaluating it as a portfolio artifact, at three depths.

## 10 minutes: does it run and is it honest?

```bash
git clone <repo-url> && cd verity-policy-coverage-eval-framework
uv sync --all-extras
PYTHONPATH=src uv run pytest tests/unit -q -p no:cacheprovider
```

Expect ~530 passed in under 30s, no API key required. Then read, in order:

1. `README.md` — "What This Proves" and "Limitations" sections. Limitations are stated
   plainly, not buried; that's the thing to notice.
2. `docs/defects-caught.md` — the seeded-defect matrix. Note that `NOT_REPRODUCED` is a
   distinct status from `CAUGHT`/`VERIFIED`, not folded into "pass".
3. `docs/adr/0001-glm-4-5-model-choice.md` — the amendment at the bottom names the gap
   between the advertised default provider and the one actually validated live.

## 30 minutes: does the evaluation machinery hold up?

Add to the above:

- `tests/semantic/conftest.py` — `record_defect_measurement` marks the test `xfail` when a
  seeded defect isn't reproduced (search for `pytest.xfail`), keeping the tier's pass/fail
  signal reserved for detector errors and control-case regressions; it does not just log a
  metric and pretend the run was green.
- `scripts/defects_report.py` — `_PASS_STATUSES` and how `NOT_REPRODUCED` is classified.
- `src/verity/statistics.py` and `docs/adr/0005-statistical-thresholds.md` — how N-sample
  aggregation and threshold_pass work, and why N differs between local/push and scheduled runs.
- `src/verity/retrieval_eval.py` and `src/verity/checks.py` (citation checking) — this is
  source-file-level and term-level, not chunk/claim-level; see Finding R2 discussion in any
  audit history for the acknowledged gap.
- Run `make test-deterministic` and `make defects-report` locally (both hermetic, no API key).

## Deep review: everything

- `docs/architecture.md` for the framework/SUT split and data flow.
- `docs/adr/` for every architectural decision and its alternatives-considered table.
- `docs/thresholds.md` and `docs/calibration-report.md` for how each metric's pass/fail
  threshold was chosen and how well it agrees with human labels.
- `datasets/golden/cases.yaml` and `datasets/adversarial/probes.yaml` for the actual test
  data — read a handful of cases end to end rather than trusting the summary counts.
- `src/sut/agent.py` for the orchestration path (auth/guardrails/retrieval/tool-calls/
  citations/review-flagging in one method — a known complexity hotspot, not hidden).
- `.github/workflows/` for what's a required PR gate vs. a scheduled/informational job.

## What to look for that would be a red flag

- A claim in `README.md` that isn't backed by a linked report or a runnable command.
- A status table (`docs/defects-caught.md`, `docs/calibration-report.md`) whose summary row
  doesn't match its own detail rows.
- A threshold or default that's stated in one doc and contradicted by the actual code
  (`src/verity/config.py`, `.env.example`, the relevant workflow YAML).
