# CI Policy: Required Checks and Release Criteria

This document is the single source of truth for what must pass before a change merges to
`main`, and what "green" actually means at each tier. See [`CONTRIBUTING.md`](../CONTRIBUTING.md)
for the day-to-day cassette/eval workflow this policy gates.

## Required status checks

The active `main-protection` repository ruleset requires all of the following
checks before a pull request can merge to `main`:

- `Lint · Type · Unit Tests (Python 3.12.15)` and
  `Lint · Type · Unit Tests (Python 3.13.16)` from
  `PR Gate (Tier 1 — lint · type · unit)`.
- `Build image and scan with Trivy` from `Container Image Scan`.
- `links-and-claims` from `Documentation checks`.

The documentation check runs when Markdown changes and rejects workstation-local file URLs and unsupported superlatives. A code-only pull request must
not assume this required context will be created; include an accurate, relevant
documentation change when the behavior itself warrants one. Do not add unrelated
text solely to manufacture a green check.

## What the required checks verify

The PR Gate matrix verifies the following on Python 3.12.15 and 3.13.16:

1. Ruff lint and formatting, then strict mypy checks on `src`.
2. Hermetic unit and deterministic tests, with an 80% global coverage floor
   and module-sensitive thresholds for agent, retrieval, metrics, tracing and
   reporting code.
3. Cassette-backed calibration and defect-report smoke checks, plus regenerated
   documentation consistency.
4. Vulnerability-exception expiry and `pip-audit`, Gitleaks secret scanning,
   and Bandit medium/high findings.
5. Native evidence emission and validation for deterministic execution; the
   Python 3.12.15 job also verifies and records the deliberate failure control.
6. `scripts/check_quarantine_policy.py`, which requires active quarantines to
   have an owner role, named reviewer, explicit `retain` disposition, reason,
   promotion criteria, and bounded review/expiry dates. The repository policy
   supplies the maximum review and expiry windows. The checker reconciles exact
   test IDs with quarantine markers throughout `tests/semantic`. It validates
   governance records, not live calibration or metric quality. A quarantine
   must only be promoted after its predeclared independent quality criteria
   are met.

`Container Image Scan` builds the packaged image and runs Trivy.
`Documentation checks` validates repository-wide Markdown links and claims.
All four ruleset checks must pass for merge. Tier 2 (semantic) and Tier 3
(adversarial) remain informational.

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

## Public clone path

The supported first-run path requires no provider credentials:

```bash
uv sync --all-extras
make test-deterministic
make defects-report
```

If the local environment blocks pytest plugin socket creation, the checks themselves can
still be exercised with plugin autoload disabled:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 UV_CACHE_DIR=/tmp/uv-cache \
  uv run pytest -q tests/unit tests/deterministic
```

This fallback is for constrained local sandboxes only. It is not the configured pull-request
gate; the GitHub workflow runs the normal command surface.

## Release criteria

A change is releasable when:

- The required Tier 1 check is green on the merge commit.
- A fresh local or CI run of `make release-check` has been captured for the commit being
  published, including timestamp, commit SHA, Python version, and pass/fail summary. Keep
  this as a release artifact or attach it to the release notes; do not rely on stale report
  screenshots as release evidence.
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

`make release-check` runs every hermetic step above in one command from a fresh clone (lint,
format check, mypy, unit + deterministic tests with coverage gates, dependency/static security
scans, and evidence regeneration) — useful as a single local pre-publish/pre-tag verification
pass, though it does not replace the actual required PR gate check.

## Changing a threshold

Coverage floors and module-sensitive thresholds are deliberately conservative and
occasionally need to move (e.g. after adding a large new module). Treat a threshold change
as a reviewable decision: explain in the PR description why the number is moving and what,
if anything, is now less covered as a result — don't lower a gate purely to make a failing
CI run pass.
