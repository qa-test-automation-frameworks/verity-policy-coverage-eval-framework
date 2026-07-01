# ADR-0003: SHA-256 Cassette Replay for CI

**Status:** Accepted

## Context

Tier-1 deterministic tests must run on every PR with:
- Zero live API calls (no secrets required, no cost, no flakiness from outages).
- Reproducible results — the same commit must produce the same pass/fail every run.
- Fast execution (target: < 3 minutes for the full Tier-1 suite).

The SUT (`CoverageAgent`) makes one or two LLM calls per answer. Without
replay, every test would require a live provider.

## Decision

Implement **VCR-style SHA-256 keyed cassette record/replay** in `verity/cassettes.py`:

- `request_key(messages, model, tools)`: deterministic SHA-256 hash of the
  JSON-serialised request parameters. The same logical request always maps to
  the same key, regardless of when or where it is run.
- `CassetteLibrary(directory)`: stores cassettes as `<key>.json` files.
  On replay, returns the stored response; on miss, raises `CassetteMissError`.
- `LLMProvider` integrates cassette mode (`record` | `replay` | `off`) via
  `verity.config.Settings`. Tests set `cassette_mode="replay"`.

Cassettes are **hand-authored** for the golden cases and adversarial probes
(see `datasets/golden/cases.yaml` and `datasets/adversarial/probes.yaml` for
current counts). The `scripts/record_cassettes.py` and
`scripts/author_adversarial_cassettes.py` scripts reproduce them without an
API key. Committing cassettes makes the test suite self-contained and forkable.

## Consequences

**Easier:**
- `make test` (Tier 1) works with zero environment setup beyond Python + uv.
- No API key is ever required to run a full CI check on a PR.
- Cassette files serve as a human-readable record of what the LLM actually said.

**Harder:**
- When the SUT prompt template changes, cassettes must be re-authored to match
  the new request hash. The `--author` flag in `record_cassettes.py` automates this.
- Cassette files add size to the repository (each is ~2-5 KB, and the count
  grows with the dataset).
- Two-turn interactions (first turn + tool-call + second turn) require two
  cassette entries keyed to different hashes.

## Alternatives Considered

| Alternative | Rejected because |
|-------------|-----------------|
| `responses` / `httpretty` HTTP mocking | Mocks HTTP layer, not the LLM logic layer; still requires a real request shape to mock against |
| `pytest-recording` (VCR.py) | YAML cassette format; harder to author by hand; less transparent |
| Injecting a fake `LLMProvider` | Cannot replay realistic token counts, costs, or tool-call structures |
