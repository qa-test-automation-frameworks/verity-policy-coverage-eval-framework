# Semantic report provenance validation

Date: 2026-10-19

## Finding

The committed `reports/semantic/results.json` is a legacy July snapshot without an embedded run timestamp or source commit. In the current Pages build, the tracked file could survive when no new semantic artifact was downloaded, allowing historical results to appear current. A merge-triggered semantic workflow also skipped evaluation because no provider key was configured. The public trend-data endpoint did not contain semantic history.

## Change

- Successful Semantic Eval runs now upload `provenance.json` with the Actions run URL/ID, recording time, and code SHA.
- The Pages workflow removes the tracked snapshot before artifact restore, then rejects any artifact whose provenance is absent, incomplete, or whose source SHA does not match the result payload. With no accepted artifact, semantic-only cases stay `COVERED`.
- The report names the provenance source and distinguishes the evaluation time from report-build time. Legacy data is explicitly described as historical.
- Unit coverage exercises missing, legacy, matching, and mismatched provenance cases.

## Validation

- Passed: four direct provenance-helper cases using Python 3.11 stdlib.
- Passed: `python3 -m py_compile scripts/defects_report.py tests/unit/test_defects_report.py`.
- Passed: Ruby YAML parse of both modified GitHub Actions workflows.
- Passed: `bash -n` on the extracted validation and semantic-evaluation shell blocks.
- Passed: `git diff --check`.
- Not run locally: `python3 -m pytest tests/unit/test_defects_report.py -q` cannot import the test conftest because system Python has no `hypothesis`; `uv sync --frozen --all-extras --offline` cannot find configured Python 3.13.16 in local managed installations. Hosted exact-head CI is required for the full test result.

No provider inference, paid call, or live semantic evaluation was performed.
