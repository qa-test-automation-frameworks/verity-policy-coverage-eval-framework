# Adversarial CI dependency verification — 2026-10-04

The adversarial job invokes pytest with `--alluredir`, so its frozen install must
select both the `dev` and `report` extras. A base `uv sync --frozen` does not select
these optional dependencies. Execution uses `uv run --no-sync` after the explicit
install to preserve the resolved environment.

The calibration job also selects `semantic`, because its live calibration
entry point imports semantic evaluation components. This change does not claim
that live calibration has executed or that a live judge is validated.

## Reproduce the no-provider suite

From the repository root, use an isolated environment outside the working tree:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/verity-adversarial-check uv sync --frozen --extra dev --extra report
UV_PROJECT_ENVIRONMENT=/tmp/verity-adversarial-check PYTHONPATH=src uv run --no-sync pytest tests/adversarial/ -m adversarial -v --alluredir /tmp/verity-adversarial-allure
```

Observed with CPython 3.13.14, pytest 9.1.1 and allure-pytest 2.16.0:
**75 collected, 75 passed**, in 1.15 seconds. The environment was installed from
`uv.lock`, rather than inherited from the existing working `.venv`. No provider
calls or credentials were used.

## Failure diagnostic control

An external temporary pytest file containing `assert False,
"EXPECTED_NEGATIVE_PROBE"` was executed with the same environment and an isolated
Allure output directory. The process returned **1** and the generated
`*-result.json` recorded `status: failed` and the expected diagnostic. This
verifies that the plugin retains failure results; it is an intentional probe,
not an additional passing application test.

Workflow artifact uploads now run under `if: always()`. The upload includes the
hermetic Allure directory and local security summaries directly, so a failed
pytest command cannot prevent diagnostics from being uploaded by skipping the
post-test summary copy. Test failure still fails the job.

Remote workflow execution and optional live-provider results require separate
verification. These local checks do not establish the precise exception in an
older inaccessible CI log.
