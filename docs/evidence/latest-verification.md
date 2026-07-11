# Current Verification Record

| Field | Value |
|---|---|
| Repository ref | `main` (refresh on the next credentialed verification PR) |
| Fast gate | `pr-gate.yml` — hermetic lint, type, unit, deterministic, security, and cassette evidence |
| Full evidence | `semantic-eval.yml` and `adversarial.yml` — credentialed/manual or scheduled |
| Current state | `evidence-unavailable` until a fresh provider-backed run is published |
| Target/environment | Fictional policy RAG + tool-use SUT; repository-controlled corpus |
| Evidence class | Hermetic detector proof plus credentialed live-provider evidence |
| Report | [Evaluation report](https://qa-test-automation-frameworks.github.io/verity-policy-coverage-eval-framework/) |
| Known limitations | [Known issues](../known-issues.md), including clean-control failures and live calibration status |

The next credentialed verification record must replace this entry with the commit
SHA, workflow run URL/ID, completion time, provider/model/judge, sample count,
corpus fingerprint, clean-control result, artifact freshness, and any approved
exception with owner and expiry. Hermetic cassette replay is not a substitute for
live provider evidence.
