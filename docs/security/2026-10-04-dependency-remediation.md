# Dependency remediation — 2026-10-04

The frozen all-extras scan remains failing. This change fixes available patch/minor advisories without suppressing unresolved findings. It is not a clean-security declaration.

## Scope and changes

Baseline: `b374d3342b1b44ab1edf31d56c40d354fb5059d5`. Native uv resolution changed these packages:

| Package | Before | After |
|---|---|---|
| aiohttp | 3.14.1 | 3.14.3 |
| anyio | 4.14.1 | 4.14.2 |
| datasets | 5.0.0 | 5.0.1 |
| litellm | 1.90.0 | 1.90.7 |
| pillow | 12.2.0 | 12.3.0 |
| pip | 26.1.2 | 26.2 |
| python-discovery | 1.4.2 | 1.6.1 |
| urllib3 | 2.7.0 | 2.8.0 |
| virtualenv | 21.5.1 | 21.7.13 |

`python-discovery` changed through virtualenv's resolver requirements. Advisory floors in `tool.uv.constraint-dependencies` prevent downgrades without adding unused dependencies. The frozen lock includes pip as a project-resolved dependency; its finding is not merely an injected scanner tool finding.

## Unsuppressed scan

Both scans used a frozen all-extras requirements export and `pip-audit -r <export> --no-deps --disable-pip --format=json --progress-spinner=off`, on Linux CPython 3.13. Both exited 1 because findings remain; neither is a scanner crash.

| Result | Baseline | After patch/minor fixes |
|---|---:|---:|
| Native advisory records | 61 | 12 |
| Unique package/advisory-ID pairs | 37 | 8 |
| Affected packages | 13 | 5 |

The advisory service repeats some IDs and aliases. Record counts are not distinct vulnerabilities. Machine-readable package/version/advisory/fix facts are retained in [baseline scan](scans/2026-10-04-before.json) and [updated scan](scans/2026-10-04-after-patch-minor.json), including scope and requirements hash; the updated scan also records the tested lock hash.

Remaining packages: chromadb 1.5.9, diskcache 5.6.3, ragas 0.4.3, oauthlib 3.3.1 and setuptools 82.0.1. The scan lists fixes for oauthlib 4.0.0 and setuptools 83.0.0; evaluate these majors separately with compatibility checks. Empty fix lists for the others require exposure/remediation investigation, not automatic acceptance. Removed expired exceptions remain archived; no replacement exclusion was introduced.

## Compatibility verification

A disposable uv environment installed `uv sync --frozen --all-extras`. The user's existing `.venv` was preserved. Runtime: Linux, CPython 3.13.14. Commands used `UV_PROJECT_ENVIRONMENT=<isolated environment>`, `UV_CACHE_DIR=<isolated cache>` and `uv run --no-sync` after installation.

- `pytest -p portfolio_cold_embedding_cache -m 'not live' -n 2 --cov=src --cov-report=term-missing --cov-report=json:<scratch coverage> --cov-fail-under=80`: **1,713 passed, 2 skipped**, eight warnings; 83.49 seconds; source coverage **94.96%**. The temporary plugin only redirects Chroma's real default ONNX cache to the independently provisioned asset. It does not replace embeddings or assertions. Skips remain visible: a documented retrieval limitation and a provider-key-dependent metric constructor.
- A subsequent governance regression addition was verified through the focused exception/quarantine suites: **32 passed**. The earlier full-suite count does not include that final additional test.
- `ruff check src tests scripts promptfoo`, `ruff format --check src tests scripts promptfoo` and `mypy src`: passed; 140 formatted files, 40 typed source files.
- `python scripts/check_module_coverage.py <scratch coverage>`: all configured critical-module gates passed.
- `PYTHONPATH=src:. python scripts/run_calibration.py --out <scratch report>`: passed for 56 authored-score replay cases. This verifies calculation/report compatibility, not live judge quality or independent human agreement.
- `PYTHONPATH=src:. python scripts/defects_report.py` and `git diff --exit-code docs/defects-caught.md`: passed; generated claims remained unchanged, including three `NOT_REPRODUCED` dispositions.
- `bandit -r src/ -ll -c pyproject.toml`: passed the configured medium/high gate; three low-severity findings remain, so this is not a zero-findings claim.

DeepEval's pytest plugin requires a local socket. The full and focused suites ran in the environment permitting that socket; the plugin was not disabled to obtain a passing result. Tool/model bootstrap requires public downloads; provider-free execution is not proof of fully offline bootstrap.

Remote validation, Python 3.12 compatibility, remaining advisories and actual live metric promotion remain separate work. These results establish the tested patch/minor environment only.
