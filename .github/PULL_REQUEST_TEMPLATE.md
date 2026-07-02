## Summary

<!-- What does this PR change and why? -->

## Evidence checklist

- [ ] `make lint` / `make format` / `make type` pass locally
- [ ] `make test` (hermetic unit + deterministic) passes locally
- [ ] If SUT behavior changed: cassettes re-recorded (`make record`) and committed
- [ ] If a golden case, threshold, or checker changed: `make defects-report` re-run and `docs/defects-caught.md` updated
- [ ] If provider/judge config changed: `docs/calibration-report.md` and README limitations reflect the actual validated path
- [ ] No secrets or API keys included in the diff

## Test plan

<!-- How did you verify this change? Commands run, manual steps, screenshots if UI/report output changed. -->
