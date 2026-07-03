# CI Policy: Required Checks and Release Criteria

This document is the single source of truth for what must pass before a change merges to
`main`, and what "green" actually means at each tier. See [`CONTRIBUTING.md`](../CONTRIBUTING.md)
for the day-to-day cassette/eval workflow this policy gates.

## Required status check

The `lint-type-test` job in `PR Gate (Tier 1 — lint · type · unit)`
(`.github/workflows/pr-gate.yml`) is required for merge. It runs as a matrix
across Python 3.12 and 3.13, which GitHub surfaces as two separate checks —
`Lint · Type · Unit Tests (Python 3.12)` and `Lint · Type · Unit Tests
(Python 3.13)`. Configure **both** as required status checks under the
repository's branch protection rules for `main`. No other workflow blocks
merges — Tier 2 (semantic) and Tier 3 (adversarial) are informational.

## What the required gate checks

Every step below must pass for `lint-type-test` to succeed:

1. **Lint** — `ruff check` and `ruff format --check` on `src` and `tests`.
2. **Type check** — `mypy --strict` on `src`.
3. **Unit + deterministic tests** — `pytest -m "not live"`, i.e. `tests/unit/`,
   `tests/deterministic/`, and `tests/adversarial/` (all hermetic, cassette-replayed, no
   API key required).
4. **Global coverage floor** — `--cov-fail-under=80` across `src/`.
5. **Module-sensitive coverage gates** — `scripts/check_module_coverage.py` enforces a
   per-module minimum for the areas most likely to hide a regression behind a healthy
   average: `sut/agent.py`, `sut/retriever.py`, `verity/metrics/*`, `verity/tracing.py`,
   `verity/reporting.py`. See that script for current thresholds.
6. **Dependency vulnerability scan** — `pip-audit` (with an explicit, reviewed ignore list
   for accepted findings).
7. **Static security scan** — `bandit -ll` (medium/high severity only).

If any step fails, the PR cannot merge. A package registry outage during `pip-audit` is
a retry or rerun situation, not an accepted-risk exception. There is no override path other
than fixing the underlying issue or, for a genuinely accepted risk (e.g. a new CVE with no
fix yet), adding it to the `pip-audit` ignore list in a reviewed PR with a comment
explaining why.

## Non-blocking tiers (informational)

- **Tier 2 — Semantic eval** (`semantic-eval.yml`): runs on merge to `main`; requires a
  provider API key as a repository secret. Publishes a report but does not block PRs —
  live-model output is not deterministic enough to gate merges on.
- **Tier 3 — Adversarial** (`adversarial.yml`): scheduled weekly; publishes the security
  summary (`reports/security/summary.md`, see [`build_report_site.py`](../scripts/build_report_site.py))
  but does not block merges. A BREACHED result on a probe whose `expected_outcome` is
  `defended` is a real finding and should be triaged promptly even though it doesn't fail CI.
  Hermetic replay uses deterministic lexical detectors; live Promptfoo runs add rubric
  assertions to catch paraphrased injection and personal-data breaches that exact-string
  checks can miss.
- **Pages** (`pages.yml`): rebuilds the static report site after Tier 1 completes and Tier
  2/3 artifacts are available. Failure here does not block merges; it means the published
  report site is stale, not that the code is broken.

## Release criteria

A change is releasable when:

- The required Tier 1 check is green on the merge commit.
- Any new seeded-defect or golden case added by the change has both a retrieval fixture and
  an authored/recorded cassette committed (see [`CONTRIBUTING.md`](../CONTRIBUTING.md)'s
  cassette workflow) — an uncommitted cassette means Tier 1 will fail for anyone else who
  checks out the branch, not just the author.
- If the change touches calibration (`scripts/run_calibration.py`) or retrieval
  (`src/sut/retriever.py`), the corresponding committed evidence
  (`docs/calibration-report.md`, `datasets/retrieval/recorded_chunks.json`) has been
  regenerated and reviewed — these are hand-triggered artifacts, not part of the automated
  gate, so a stale artifact will not fail CI on its own.
- Any Tier 3 BREACHED result introduced or changed by the PR is either expected (an
  intentionally seeded defect the PR is demonstrating) or has been triaged and is being
  tracked, not silently ignored.

## Changing a threshold

Coverage floors and module-sensitive thresholds are deliberately conservative and
occasionally need to move (e.g. after adding a large new module). Treat a threshold change
as a reviewable decision: explain in the PR description why the number is moving and what,
if anything, is now less covered as a result — don't lower a gate purely to make a failing
CI run pass.
