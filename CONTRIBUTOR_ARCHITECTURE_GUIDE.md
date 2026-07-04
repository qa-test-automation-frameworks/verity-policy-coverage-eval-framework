# Contributor Architecture Guide

## First Run

```bash
uv sync --all-extras
make test-deterministic
make defects-report
```

The deterministic path is the supported first-run path. It uses committed cassettes and local
fixtures, so it does not require provider credentials.

## Project Map

| Area | Purpose |
| --- | --- |
| `src/verity/` | Evaluation framework: providers, metrics, cassettes, reporting, tracing, and calibration |
| `src/sut/` | Demonstration target: corpus, retrieval, coverage tool, guardrails, and response flow |
| `datasets/golden/` | Versioned expected-behavior cases |
| `datasets/calibration/` | Judge-calibration examples and replay cassettes |
| `datasets/cassettes/` | Recorded responses for deterministic replay |
| `tests/deterministic/` | No-key regression checks for seeded defects and guardrails |
| `tests/semantic/` | Provider-backed semantic checks |
| `docs/` | Reviewer guides, thresholds, reports, and operating notes |

## Change Workflow

1. Update the smallest dataset, source, or documentation surface needed for the change.
2. Run the narrow deterministic command that covers the changed area.
3. Regenerate derived reports when source data changes.
4. Keep provider-backed runs informational unless the change explicitly updates semantic evidence.

## Evidence Rules

- Dataset changes should cite the case id and regenerated report.
- Threshold changes should cite calibration output and any independent label review.
- Provider-backed evidence should include provider, model, date, and command.
