# Separately tested security majors — 2026-10-04

OAuthlib 3.3.1 → 4.0.0 and setuptools 82.0.1 → 83.0.0 are isolated from the preceding patch/minor update. Native uv resolution changes only these two package versions; corresponding constraint floors prevent downgrade. No assertions, snapshots or scanner exclusions changed.

The upstream advisories identify [OAuthlib's PKCE comparison fix](https://github.com/advisories/GHSA-xpv3-w29h-x7cv) in 4.0.0 and [setuptools' source-distribution exclusion fix](https://github.com/advisories/GHSA-h35f-9h28-mq5c) in 83.0.0. This repository does not implement an OAuth authorization server; upgrading still removes the resolved finding rather than relying on a presumed unexposed path.

## Executed compatibility checks

Installed the frozen all-extras lock in the same disposable Linux CPython 3.13.14 environment described in [patch/minor verification](2026-10-04-dependency-remediation.md), using `uv run --no-sync` for execution.

- Full `pytest -p portfolio_cold_embedding_cache -m 'not live' -n 2 --cov=src --cov-report=term-missing --cov-report=json:<scratch coverage> --cov-fail-under=80`: **1,714 passed, 2 skipped**, eight warnings, 68.04 seconds, **94.96%** coverage. This includes the final added governance regression. Same real ONNX model/cache and unchanged plugins; no paid provider calls.
- Critical-module coverage gates, Ruff lint/format and strict mypy: passed.
- Authored-score calibration replay: 56 cases, pipeline passed; no live judge validation inferred.
- `python -m build --outdir <scratch directory>`: isolated wheel and source-distribution build passed. The first restricted attempt failed DNS while fetching hatchling, before build execution; the authorized network-enabled attempt succeeded. Packaging bootstrap requires public dependencies.

The full suite provides runtime/import compatibility evidence for these transitive majors. It does not prove every OAuthlib consumer mode or reproduce the macOS-specific setuptools vulnerability on Linux. Remote Python 3.12 validation remains separate.

## Remaining scan findings

The unsuppressed frozen all-extras scan completed with exit **1**: **9 native records, 6 unique package/advisory-ID pairs, 3 affected packages**. OAuthlib and setuptools no longer have findings in this scan. [Version/advisory facts and tested lock hash](scans/2026-10-04-after-major-fixes.json) preserve the result.

Chroma 1.5.9, DiskCache 5.6.3 and RAGAS 0.4.3 still require exposure/remediation review. Empty scanner fix lists do not establish non-exploitability or justify an exception. No expired exception was renewed; CI must retain the failure until remediation or a valid reviewed exception exists. No clean-security or live-quality claim is made.
