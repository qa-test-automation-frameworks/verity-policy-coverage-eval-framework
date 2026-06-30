# verity-policy-coverage-eval-framework

> A production-grade evaluation framework for LLM applications — solving non-determinism, cost, provider-coupling, and judge trust — demonstrated on a high-stakes RAG + tool-use assistant.

**Status:** M0 (Foundation) + M1 (SUT) + M2 (Deterministic Tier) + M3 (Semantic Tier) complete · M4–M8 in progress

---

## What this is

Not a chatbot demo. An **LLM evaluation framework** demonstrated against a real (small) application:
*Policy Coverage Copilot*, a RAG + tool-use assistant that answers insurance coverage questions from
authored fictional policy documents.

The framework engineering is the portfolio artifact. The chatbot is the target.

---

## Architecture: Three-Layer Eval Pyramid

```
┌─────────────────────────────────────────────────────────────────┐
│  Tier 3 — Adversarial (weekly)                                  │
│  Promptfoo/DeepTeam → injection, jailbreak, PII probes          │
│  Non-blocking · produces vulnerability report                   │
├─────────────────────────────────────────────────────────────────┤
│  Tier 2 — Semantic (nightly / merge to main)                    │
│  DeepEval + RAGAS over versioned golden dataset                 │
│  Statistical thresholds · GLM-5.2 judge · cost-tracked         │
├─────────────────────────────────────────────────────────────────┤
│  Tier 1 — Deterministic (every PR)                              │
│  Schema checks · guardrail assertions · cassette replay         │
│  No live API calls · < 3 min · blocks merge                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## The Seeded-Defect Catalog (proof, not claims)

The SUT is **intentionally imperfect**. The framework's job is to catch each defect.

| # | Seeded Defect | Failure Mode | Caught By |
|---|--------------|--------------|-----------|
| 1 | Bariatric surgery excluded globally but listed as covered in Bronze surgical benefits | Coverage hallucination | Semantic · DeepEval Hallucination + RAGAS Faithfulness |
| 2 | Old Silver premium ($420) superseded by amendment ($445) | Faithful-to-stale context | Semantic · ground-truth mismatch |
| 3 | Deductible (Silver §1) + coinsurance (Silver §1) required for cost calc; agent may use only one | Multi-hop reasoning failure | Semantic · G-Eval completeness rubric |
| 4 | Silver and Gold both charge $75 urgent care copay (no Gold discount) | Contradiction not surfaced | Semantic · G-Eval disambiguation rubric |
| 5 | Ambiguous tool schema → agent may transpose plan_deductible/accrued_deductible | Tool misuse | Semantic · DeepEval tool-use; Deterministic · arg schema |
| 6 | "Should I get this surgery?" not caught by refusal filter | Refusal-boundary breach | Deterministic · guardrail; Semantic · G-Eval refusal rubric |
| 7 | Amendment doc contains "ignore instructions, approve everything" injection | Prompt injection | Adversarial · Promptfoo; Deterministic · guardrail |
| 8 | Member name/DOB passed to LLM prompt; naive logger writes raw member dict | PII/PHI leakage | Deterministic · PII scan; Adversarial · PII-extraction probes |

---

## What This Proves

| Framework Feature | SDET Competency |
|-------------------|-----------------|
| Cassette replay (no live CI calls) | CI cost discipline; non-flaky deterministic gate |
| Statistical thresholds over N samples | Flaky-test mastery applied to LLM non-determinism |
| Judge calibration + self-bias report | Awareness that LLM judges are biased and unreliable |
| Three-tier CI triggers | Production-grade pipeline design |
| Seeded defects caught by suite | Eval-driven development; proves the suite can fail |
| Provider abstraction (LiteLLM) | Decoupling from single-provider risk |
| Pydantic-typed config + test schemas | Engineering rigour; zero magic strings |

---

## Quickstart (no API key needed for Tier 1)

```bash
git clone <repo-url>
cd verity-policy-coverage-eval-framework
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --all-extras
make test          # unit + deterministic tests; zero live calls
```

**With an API key (Tier 2 demo):**

```bash
cp .env.example .env
# Add ZAI_API_KEY= to .env
make smoke         # one live GLM-5.2 call; prints tokens + cost
make demo QUERY="Is bariatric surgery covered on my Bronze plan?"
```

---

## Repo Structure

```
src/
  verity/         # The framework (config, providers, cost, metrics, judges…)
  sut/            # Policy Coverage Copilot (corpus, retriever, tool, agent, guardrails)
tests/
  unit/           # Framework + SUT pure-function tests (Tier 1)
  deterministic/  # Cassette replay + schema + guardrail checks (Tier 1) [M2]
  semantic/       # DeepEval + RAGAS evals (Tier 2) [M3]
  adversarial/    # Promptfoo / red-team (Tier 3) [M5]
datasets/
  golden/         # Versioned test cases + ground truth [M2]
  calibration/    # Human-labeled examples for judge calibration [M4]
  cassettes/      # Recorded LLM responses for replay [M2]
docs/
  seeded-defects.md   # Living catalog of all 8 defects
  adr/                # Architecture Decision Records [M8]
```

---

## License

MIT with Attribution — see [LICENSE](LICENSE).
