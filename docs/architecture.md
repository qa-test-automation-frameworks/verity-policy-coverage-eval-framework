# Architecture

See the three-layer eval pyramid diagram in [README.md](../README.md).

Full architecture diagram and component walk-through will be added in M8 (Documentation & Polish).

## Key design decisions

Architecture Decision Records (ADRs) will be committed in M8 under `docs/adr/`. Planned ADRs:

| ADR | Decision |
|-----|---------|
| 0001 | Why GLM-5.2 (cost, OpenAI-compat, Z.ai/OpenRouter/Together portability) |
| 0002 | Three-layer eval pyramid (solves non-determinism, cost, provider-coupling) |
| 0003 | Cassette replay for CI (zero live calls on PRs; fast; reproducible) |
| 0004 | Judge calibration and self-bias measurement |
| 0005 | Statistical thresholds vs single-run brittle assertions |
