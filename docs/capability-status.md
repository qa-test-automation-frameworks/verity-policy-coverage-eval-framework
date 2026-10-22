# Capability Status

<!-- current-evidence:start -->
## Current evidence

The inventory is generated from `portfolio/current-evidence.json`; its source snapshot is `4f1376be5e6a53be223e611a3072acca9d640b34`.
The current golden corpus has **69 cases** (version `1.0.0`; hash `ec79360e2a25…`).

- **Synthetic rubric replay:** The 2026-07-04 report replays 56 hand-authored cases across seven metrics; it demonstrates methodology and is not live calibration.
  See [`docs/calibration-report.md`](calibration-report.md).
- **Historical live rubric:** The archived 2026-07-02 report records 32 live rubric cases with openrouter/openai/gpt-4o-mini; it reports 75% faithfulness agreement and MAE 0.238. The native run ID was not retained.
  See [`reports/calibration/archive/live-2026-07-02/calibration-report.md`](../reports/calibration/archive/live-2026-07-02/calibration-report.md).
- **Live runtime adapter artifact:** The retained semantic report shows 56 outcomes (46 passed, 10 failed) and 14 measurements, including 40 controls (30 passed, 10 failed); its run ID and execution date are missing.
  See [`reports/semantic/results.json`](../reports/semantic/results.json).

Hallucination polarity: the raw DeepEval runtime score is `lower_is_better`; the separately named calibration score `hallucination_groundedness` (dataset label `hallucination`) is `higher_is_better`.
<!-- current-evidence:end -->

| Capability | Status | Evidence |
| --- | --- | --- |
| Deterministic replay | Enforced | `make test-deterministic` |
| Unit and framework checks | Enforced | `make test` |
| Defect report generation | Enforced by source data | `make defects-report` |
| Calibration replay | Supported | `make calibrate` |
| Semantic provider run | Informational | `make eval-semantic` |
| Adversarial provider run | Informational | `make redteam` |

The evidence summary above is generated from `portfolio/current-evidence.json`. Run
`uv run python scripts/check_current_evidence.py` to validate its hashes, dataset counts,
polarity, and required evidence headers; add `--write-summary` after an intentional manifest
update. This consistency check does not independently establish that a report's claims are true.

## Feature currency review — 2026-10-19

This review records concrete retain/defer decisions against the current implementation and upstream documentation. It does not imply that a feature is safe merely because the code path is present, nor that optional provider evaluations ran.

| Capability | Current implementation | Official support checked | Benefit and compatibility risk | Decision and proof |
| --- | --- | --- | --- | --- |
| Python and uv runtime selection | Python 3.12 and 3.13 are supported. The PR-gate job sets `UV_PYTHON` from the active matrix leg so each `uv run` remains on the interpreter installed for that leg. | [uv Python version selection](https://docs.astral.sh/uv/concepts/python-versions/) documents interpreter selection and project pin behavior. | The matrix exercises both supported runtimes. Runtime drift from an unconstrained `uv` version can still change resolution/behavior; changing the Python versions requires lock and native CI checks. | **Retain 3.12/3.13.** Current main PR Gate `39208392703` passes both versions, including quarantine reconciliation and dependency scanning. |
| Ruff lint and formatting | Main pins Ruff `0.17.1`; `pyproject.toml` explicitly sets `target-version = "py312"`. | The [Ruff 0.17.1 release](https://github.com/astral-sh/ruff/releases/tag/0.17.1) was published 2026-10-15. Its [breaking-change notes](https://github.com/astral-sh/ruff/blob/0.17.1/BREAKING_CHANGES.md) state the new default Python target; the repository's explicit setting avoids relying on that default. | The update includes current rule/formatter fixes while preserving the declared Python 3.12 lint target. A stricter/new rule may expose findings, so CI lint and format checks remain required. | **Adopt.** Ruff 0.17.1 `check .`, `format --check .`, and `uv lock --check` passed locally. PR #26 passed Trivy `39210640753`, documentation `39210640855`, Python 3.12/3.13 `39210640873`, and shared-app `39210640775`, then merged to main as `347532c`. |
| Local vector retrieval and embedding | Main uses FastEmbed `0.9.0` with the local ONNX model (`sentence-transformers/all-MiniLM-L6-v2`) and a transactional SQLite index keyed by corpus fingerprint and embedder version. No vector network service is started. | FastEmbed's [PyPI release record](https://pypi.org/project/fastembed/) reports `0.9.0`; its [supported-model catalog](https://qdrant.github.io/fastembed/examples/Supported_Models/) lists the same MiniLM model. | SQLite-backed brute-force cosine search is appropriate for this 62-chunk fictional corpus, not a large index. Model files still require a first-run download and are cached locally. The replacement preserved ordered chunk IDs for all 16 benchmark queries. | **Retain FastEmbed/SQLite.** PR #31 merged this change; its main PR Gate, shared-app, image scan, and report publication passed. Chroma was removed from the lock and active ignore files. |
| Tool schema and authorization boundary | The assistant exposes one coverage-calculator schema, validates its arguments in target-owned code, rejects unexpected/multiple calls, and keeps synthetic member authorization in the application/API rather than trusting model-selected identity. | [Pydantic model validation](https://docs.pydantic.dev/latest/concepts/models/) is used for typed request/response data; the shared reference application's API checks member-scoped access independently of the assistant. | Explicit schemas and server-side scope reduce hallucinated tool and cross-member access risk. More autonomous agent loops would add state, provider variance and extra authorization paths. | **Retain the single-round bounded tool. Defer agent-framework adoption.** Shared-app run `39028982451` passes pinned-image startup, member-isolation and citation retrieval with a stubbed provider; it makes no live model-quality claim. |
| Semantic and adversarial evaluation | Semantic evaluation is optional and separates replay from provider calls. The lock resolves DeepEval and RAGAS; RAGAS adapters use the legacy `ragas.metrics` path and contain a compatibility shim. Promptfoo live red-team runs are separate from hermetic adversarial tests. | RAGAS [metric catalog](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) documents supported metrics; the [RAGAS advisory](https://github.com/advisories/GHSA-95ww-475f-pr4f) still lists no patched release and covers multimodal URL and local-file processing. | Current factories use text metrics only. Ruff bans the vulnerable optional import paths, and the Tier-1 image omits the semantic extra; semantic CI still installs it. DiskCache's [pickle advisory](https://github.com/advisories/GHSA-w8v5-vhqr-4h9v) has no patched release; the application does not instantiate its cache backend. | **Retain the bounded metric set and exact exceptions through 2026-11-17.** Owner and non-contributing AI review are recorded; the owner explicitly accepted AI-assisted review for this portfolio gate. This is not human review or adoption. No extra provider call or spend is assumed. |
| Container runtime and OS packages | The image is digest-pinned, omits the optional semantic extra, and runs the packaged Tier-1 suite as a non-root user. The runtime copies the supported Python interpreter into a digest-pinned Distroless base. | The last retained [Container Image Scan](https://github.com/qa-test-automation-frameworks/verity-policy-coverage-eval-framework/actions/runs/39208879540) ran the expiry check, packaged tests, Trivy scan, and retained findings on source `ed71b7e`. | The audited source snapshot `4f1376be5e6a53be223e611a3072acca9d640b34` includes the semantic-free image definition, but is newer than the retained scan. That scan does not establish the current image contents. | **Retain the digest-pinned image and full gates.** An exact-snapshot build, packaged Tier-1 run, and Trivy scan remain pending; no vulnerability is claimed fixed. |

Main no longer contains ChromaDB and `.trivyignore` has no active IDs. `.pip-audit-ignore` retains only the two owner-approved DiskCache and RAGAS IDs, expiring 2026-11-17; both advisories still list no patched release. Ruff 0.17.1 merged in PR #26 as `347532c`, and Hypothesis 6.170.2 merged in PR #24 as `b5c9420`. The owner accepted the non-contributing AI-assisted review with an explicit waiver of the former human-review requirement. The semantic-free Tier-1 image definition is present in this source snapshot; exact-snapshot container proof remains pending as shown above. No upstream vulnerability is claimed fixed.
