# Current Verification Record

| Field | Value |
|---|---|
| Repository ref | `main` @ [`a9de8e6`](https://github.com/qa-test-automation-frameworks/verity-policy-coverage-eval-framework/commit/a9de8e6b7d4181448b11bd4294a6ad440090e479) |
| Fast gate | [`pr-gate.yml` run 29137796809](https://github.com/qa-test-automation-frameworks/verity-policy-coverage-eval-framework/actions/runs/29137796809) — hermetic lint/type/unit gate; completed 2026-07-11T03:20:56Z |
| Full evidence | [`semantic-eval.yml` run 29137796817](https://github.com/qa-test-automation-frameworks/verity-policy-coverage-eval-framework/actions/runs/29137796817) — completed successfully but **skipped the credentialed judge tier** because no `VERITY_PROVIDER` secret was configured on this run |
| Current state | `review-ready` for the hermetic gate; the live semantic/judge tier has no verified result for this SHA |
| Target/environment | Fictional policy RAG and tool-use SUT, repository-controlled |
| Evidence class | Hermetic and credentialed |
| Result counts | 1,683 pytest cases: 1,679 passed, 0 failed, 4 skipped (52.72s, Python 3.13) |
| Report | [Reports](https://qa-test-automation-frameworks.github.io/verity-policy-coverage-eval-framework/) (published only when provider provenance is complete) |
| Known limitations | [Known issues](../known-issues.md) |

The machine-readable record with the exact SHA, run IDs/URLs, conclusions, and
result counts — including the explicit disposition of the skipped semantic-eval
run — is published at [`latest-verification.json`](latest-verification.json).
A passing hermetic gate does not imply a live-provider judge run occurred.
