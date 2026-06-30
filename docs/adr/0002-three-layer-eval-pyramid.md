# ADR-0002: Three-Layer Evaluation Pyramid

**Status:** Accepted

## Context

LLM evaluation faces four structural problems that a flat single-tier suite
cannot solve simultaneously:

1. **Non-determinism** — the same prompt produces different outputs on each
   call; a single boolean pass/fail is unreliable.
2. **Cost** — semantic metrics require real LLM judge calls; running them on
   every PR is prohibitively expensive.
3. **Provider coupling** — if every test makes live API calls, the suite breaks
   whenever the provider has an outage or changes pricing.
4. **Judge trust** — LLM-as-judge is itself a model that can be wrong or
   biased; its reliability must be measured before it is trusted.

A single-tier suite optimized for one dimension (e.g., speed) fails the others.

## Decision

Adopt a **three-tier pyramid** with distinct cadences, costs, and failure signals:

| Tier | Name | Trigger | Tools | Live calls |
|------|------|---------|-------|------------|
| 1 | Deterministic | Every PR | Schema, refusal, tool-arg, PII, injection checks; cassette replay | None |
| 2 | Semantic | Push to main + nightly | DeepEval G-Eval, RAGAS; statistical thresholds over N samples | Yes (judge LLM) |
| 3 | Adversarial | Weekly + on-demand | Promptfoo red-team; hermetic probes | Optional |

Tier 1 **blocks merge**; Tier 2 and 3 are **non-blocking** signals that inform
the development team.

## Consequences

**Easier:**
- Every PR runs in under 3 minutes with zero live API calls.
- Semantic regressions are caught nightly before they accumulate.
- Adversarial vulnerabilities are reported weekly without blocking development velocity.
- Each tier catches a different class of defect (see `docs/defects-caught.md`).

**Harder:**
- Three separate test suites require separate fixtures, conftest wiring,
  and CI workflows.
- A defect that manifests only at the semantic level (defects #1-#4) is not
  caught until the nightly run.

## Alternatives Considered

| Alternative | Rejected because |
|-------------|-----------------|
| All-semantic, one tier | Live calls on every PR; too slow and too expensive |
| Deterministic only | Cannot detect hallucination or multi-hop reasoning failures |
| Continuous live eval per PR | $5-$50 per PR depending on suite depth; prohibitive for open-source repos |
