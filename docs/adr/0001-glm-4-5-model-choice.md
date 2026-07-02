# ADR-0001: GLM-4.5 as the Primary LLM

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

Use **GLM-4.5** (Zhipu AI / Z.ai) routed through **Z.ai** as the primary provider,
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
- Cost is low relative to frontier models; see the price table in
  `verity/cost.py` for the reference rate used by cost accounting, and
  verify current pricing on Z.ai before treating a run's cost total as exact.

**Harder:**
- Performance on complex multi-hop reasoning (defects #3, #4) depends on
  the judge model quality. A weaker judge may under-score correct answers.
- Self-bias risk: using the same model family as both SUT and judge inflates
  agreement metrics. ADR-0004 defines the measurement method; live empirical calibration remains pending.

## Alternatives Considered

| Alternative | Rejected because |
|-------------|-----------------|
| GPT-4o / GPT-4-turbo | 10-50x higher cost; harder to self-host or reproduce at zero cost |
| Local Llama 3 via Ollama | No hosted API; CI runners cannot run 8B+ parameter models reliably |
| Single provider (Z.ai only) | Tight coupling; if Z.ai pricing or availability changes the whole suite breaks |

## Amendment (2026-07-02): default path unvalidated live, substitute path is the verified one

`VERITY_PROVIDER=zai` / `VERITY_MODEL=glm-4.5` remains the default in
`Settings` and `.env.example` for the reasons above, and hermetic Tier-1/
Tier-3 tests pin GLM-4.5 internally regardless of this setting. However, at
the time of this amendment the live Tier-2 route to GLM-4.5 (via both Z.ai
and NVIDIA NIM) had not been successfully exercised end-to-end — see the
Limitations section of `README.md` and `docs/calibration-report.md` for the
specific errors hit. The committed live Tier-2 evidence and calibration
report both use `VERITY_PROVIDER=openrouter VERITY_MODEL=openai/gpt-4o-mini`
instead, which is currently the only provider/model combination with a
verified, reproducible live run in this repo.

Anyone re-validating the default should run `make eval-semantic` and
`make calibrate-live` with a working GLM-4.5 key and, if it succeeds,
update `docs/calibration-report.md` and `docs/defects-caught.md` in place;
if it does not, capture the failure mode here rather than silently
substituting a different model.
