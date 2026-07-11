# Planned Work

Concrete next steps this repository has not done yet, kept separate from the honesty-first
`docs/known-issues.md` (tracked gaps in current behavior) and `docs/thresholds.md` (per-metric
calibration status). Each item below names the exact command or file that would close it.

## Live evidence gaps

- **Validate the default provider live.** `Settings.provider`/`Settings.model` default to
  `openrouter`/`openai/gpt-4o-mini` (the only pairing with a committed live run today — see
  `docs/adr/0001-glm-4-5-model-choice.md`). Run `make eval-semantic` and `make calibrate-live`
  with a working `VERITY_ZAI_API_KEY` (zai/glm-4.5), and if it succeeds, update
  `docs/calibration-report.md` and `docs/defects-caught.md` in place.
- **Measure agreement for the newly authored calibration metrics.** `hallucination`,
  `answer_relevancy`, and `context_precision` each have 8 calibration cases and hermetic
  authored-score cassettes (`datasets/calibration/labeled.yaml`, `make calibrate`), but no live
  judge run has measured agreement against them yet — only `completeness`, `disambiguation`,
  `refusal`, and `faithfulness` have a live measurement. Run `make calibrate-live` and update
  `docs/thresholds.md`'s Calibration column from "cases authored; agreement measurement pending
  a live run" to a measured PASS/REVIEW status.
- **Produce a clean control run.** The committed `reports/semantic/results.json` run has 10 of
  40 control-tier nodes failing, concentrated on faithfulness and answer relevancy (see
  `docs/thresholds.md`'s "Committed live run: control-case failures"). A fresh `make
  eval-semantic` run after the faithfulness rubric refinement (see
  `src/verity/metrics/rubrics.py`'s `FAITHFULNESS_RUBRIC`) would show whether the refinement
  actually reduces the control failure rate — that's the evidence needed to lift the
  `@pytest.mark.quarantine` markers on `test_clean_faithfulness` and `test_answer_relevancy`
  (KI-3 in `docs/known-issues.md`).
- **Reproduce defects #1–#3 live with the default pairing.** The committed run marks these
  `NOT_REPRODUCED` for `openrouter/openai/gpt-4o-mini` — a fact about that model's quality, not
  a detector gap (the hermetic/adversarial replay proves the detectors fire). Re-running against
  a different model may or may not reproduce them; either outcome is worth recording.

## Sample-size and scale

- **N>1 on the on-demand `workflow_dispatch` path.** `semantic-eval.yml`'s manual trigger still
  uses `VERITY_SEMANTIC_SAMPLES=1` like push runs; only the nightly schedule uses N=5. Consider
  a `samples` input on `workflow_dispatch` so a reviewer triggering the workflow manually can
  opt into the full distribution-over-N statistics (see ADR-0005).
- **Grow the golden dataset further.** 69 golden cases today, up from 41 — still sized to demonstrate
  the evaluation patterns, not to measure production model quality. `docs/dataset-coverage.md`
  shows where the thinnest categories are (currently `limits`); add cases there first.
- **Grow the adversarial probe corpus further.** 71 probes across 9 categories today, up from
  20. `scripts/author_adversarial_cassettes.py`'s `_SINGLE_TURN_CONTENT` pattern is mechanical
  enough to extend per-category as new attack framings are identified.

## Domain modeling

- **Pre-existing-condition-style constraints.** The corpus models waiting periods (rider
  purchase-date based) and lifetime/annual limits, but not an ACA-incompatible pre-existing-
  condition lookback — a deliberate choice to keep the fictional policy realistic to actual US
  health plans (which cannot exclude pre-existing conditions). If a future scenario wants this
  concept anyway, model it as a rider-specific look-back rather than a base-plan exclusion, to
  keep the rest of the corpus internally consistent.

## Framework

- **Retrieval backend diversity.** `Retriever` is a `Protocol` with two concrete embedding-based
  implementations — `PolicyRetriever` (Chroma-backed) and `InMemoryCosineRetriever`
  (numpy array + brute-force cosine similarity) — plus the fixture-backed test double, all
  proven against the same benchmark contract in `tests/deterministic/`.
- **Wire `pass_rate_wilson_interval` more broadly.** Currently surfaced in semantic test failure
  messages and evidence payloads when `n > 1`; consider also rendering it in a future nightly
  trend summary once the nightly N=5 schedule accumulates enough runs to make a trend chart
  meaningful.
