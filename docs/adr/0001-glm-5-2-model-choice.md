# ADR-0001: GLM-5.2 as the Primary LLM

**Status:** Accepted

## Context

The framework needs a capable LLM for two distinct roles:

1. **SUT runtime** — the Policy Coverage Copilot answers member questions.
2. **Judge** — DeepEval G-Eval and RAGAS metrics require an LLM to score
   responses against rubrics. The judge model must be able to follow
   structured scoring prompts reliably.

Requirements:
- Low inference cost (the semantic suite and calibration runs make many calls).
- OpenAI-compatible API so the same code works across multiple hosting providers
  (no provider lock-in).
- Available on at least two independent hosting backends to allow fallback and
  price comparison.
- Sufficient instruction-following quality to act as a G-Eval judge.

## Decision

Use **GLM-5.2** (THUDM ChatGLM) routed through **Z.ai** as the primary provider,
with **OpenRouter** and **Together AI** as documented fallback options.

All provider routing goes through **LiteLLM**, which presents a single
OpenAI-compatible interface regardless of which backend is active. Switching
providers requires only a change to `VERITY_PROVIDER` and the corresponding
API key — no code change.

## Consequences

**Easier:**
- A single `LiteLLM.complete()` call works for all providers.
- `LLMProvider` in `verity/providers.py` is provider-agnostic; new backends
  can be added to the price table in `verity/cost.py` without changing any
  other module.
- Cost is very low: GLM-5.2 is priced at $1.40/M prompt tokens and
  $4.40/M completion tokens on Z.ai — a full semantic suite run costs under $0.05.

**Harder:**
- Performance on complex multi-hop reasoning (defects #3, #4) depends on
  the judge model quality. A weaker judge may under-score correct answers.
- Self-bias risk: using the same model family as both SUT and judge inflates
  agreement metrics. This is explicitly measured in ADR-0004.

## Alternatives Considered

| Alternative | Rejected because |
|-------------|-----------------|
| GPT-4o / GPT-4-turbo | 10-50x higher cost; harder to self-host or reproduce at zero cost |
| Local Llama 3 via Ollama | No hosted API; CI runners cannot run 8B+ parameter models reliably |
| Single provider (Z.ai only) | Tight coupling; if Z.ai pricing or availability changes the whole suite breaks |
