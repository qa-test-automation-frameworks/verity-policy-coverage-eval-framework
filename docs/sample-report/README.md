# Sample Report

A point-in-time snapshot of the report site, generated 2026-07-03 from data
already committed in this repo (hermetic test runs, `reports/semantic/results.json`,
`docs/defects-caught.md`). It is not auto-updated — open the HTML files directly
or serve this directory to browse it.

Live, continuously updated report: https://qa-test-automation-frameworks.github.io/verity-policy-coverage-eval-framework/

Pages included:

- `index.html` — defects-caught landing
- `calibration.html` — judge calibration report
- `cost.html` — token/cost summary (placeholder here; only populated by a live eval run)
- `vulnerabilities.html` — seeded-defect adversarial design catalog
- `security.html` — measured adversarial run summary
- `trends.html` / `trends-data/` — local/CI trend history
- `dataset-coverage.html` — golden dataset coverage matrix

The Allure HTML report is omitted — it requires the Allure CLI, which isn't
available in this snapshot's build environment. The live Pages site builds it
in CI via `pages.yml`.
