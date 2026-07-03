# OWASP LLM Top 10 Coverage Map

Maps this repository's adversarial probes, deterministic checks, semantic metrics, and CI
workflows against the [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/).
This is a coverage map, not a certification — it states what is tested and where, and is
explicit about what is out of scope for a demo-scale repository.

| # | Risk | Coverage | Evidence |
|---|------|----------|----------|
| LLM01 | Prompt Injection | Covered | Seeded defect #7 (`src/sut/corpus/amendments.md` §A5); `injection` category — 10 probes in `datasets/adversarial/probes.yaml`; `verity.checks.scan_injection`/`check_injection` (deterministic); DeepEval `InjectionCompliance` G-Eval (semantic, paraphrase-resistant); Promptfoo `not-contains` + `llm-rubric` assertions in `promptfoo/redteam.yaml` |
| LLM02 | Insecure Output Handling | Partially covered | `verity.checks.check_no_adjudication_language` blocks the assistant from presenting itself as a claims decision-maker; `adjudication_language` category — 7 probes. No downstream code-execution or markup-rendering surface exists in this demo to test insecure-output-into-a-sink scenarios (`sut.agent` returns plain text to a CLI/report, not to a renderer) |
| LLM03 | Training Data Poisoning | Out of scope | This repository uses hosted third-party models via LiteLLM; it does not train or fine-tune, so poisoning the base model is not a risk surface it controls. Corpus poisoning (a malicious policy document) is covered instead under LLM01/LLM08 below |
| LLM04 | Model Denial of Service | Covered | `verity.config.Settings.timeout`/`retries` bound each call; `verity.latency` enforces per-tier latency budgets (`DETERMINISTIC_BUDGET_MS`, `LIVE_BUDGET_MS`) as a regression tripwire; `resource_exhaustion` category — `adv-resourceexhaustion-001` probes a pathologically long, repetitive input and asserts the agent completes and returns a well-formed response rather than crashing or falling back to a failure path |
| LLM05 | Supply Chain Vulnerabilities | Covered | `pip-audit` in the required PR gate with a dated, reviewed `.pip-audit-ignore` (`scripts/check_vuln_exceptions.py` fails CI on an expired exception); `bandit` static scan; SHA-pinned GitHub Actions; digest-pinned Docker base image; Trivy container scan (`docker-scan.yml`); Dependabot on docker/actions/uv |
| LLM06 | Sensitive Information Disclosure | Covered | Seeded defect #8 (PII in prompt/logs); `verity.checks.scan_pii`/`check_pii` (deterministic, context-gated DOB pattern) and DeepEval `PIILeakage` G-Eval (semantic, catches paraphrased disclosure); `pii_extraction` category — 12 probes including cross-member confidentiality; `verity.checks.scan_prompt_leakage`/`check_prompt_leakage` for leaked system instructions and a canary secret embedded in retrieved context (`adv-canary-001`..`003`) for leaked internal reference data — both under `prompt_extraction`, 8 probes total; `verity.tracing.hash_identifier` keeps raw member IDs out of trace spans |
| LLM07 | Insecure Plugin Design | Covered | `sut.tools.coverage_calculator.CoverageInput` (Pydantic-typed, bounded tool schema); `verity.checks.check_tool_args` (deterministic arg-value/transposition check, seeded defect #5); unknown-tool calls and malformed arguments fail closed in `sut.agent._handle_tool_call_round`; `tool_abuse` category — 8 probes (nonexistent tools, repurposed tool calls, out-of-domain arguments) |
| LLM08 | Excessive Agency | Covered | The agent supports exactly one tool, one round of tool calls, and no autonomous multi-step planning (`docs/architecture.md`'s `agent.answer()` data flow); a second round of tool calls in the same turn is explicitly rejected (`sut.agent._handle_tool_call_round`) rather than trusted; `verity.checks.check_no_adjudication_language` and the human-review gate (`sut.agent.CoverageAgent.deliver`/`review_triggers.py`) prevent the agent from acting as a final decision-maker |
| LLM09 | Overreliance | Partially covered | `SECURITY.md` and the system prompt both state the assistant does not adjudicate claims; `check_no_adjudication_language` enforces this in the response text; judge calibration (`docs/calibration-report.md`) quantifies how much the automated judge itself should — and should not — be trusted, which is the overreliance risk turned inward on the eval framework. No user-facing confidence/uncertainty score is surfaced in `AgentResponse` today |
| LLM10 | Model Theft | Out of scope | No proprietary model is hosted or served by this repository; all inference is a hosted third-party API call via LiteLLM, so model-weight exfiltration is not a risk surface it controls |

## Reading this table

- **Covered** — a specific probe, check, or metric exists and is exercised by a committed test
  (hermetic and/or live).
- **Partially covered** — some control exists, but the risk has a dimension this repository does
  not test (usually because the relevant surface — code execution, fine-tuning, a confidence UI —
  doesn't exist in this demo).
- **Out of scope** — the risk applies to a capability (model training, model hosting) this
  repository does not have.

## Where to look

- `datasets/adversarial/probes.yaml` — the probe corpus itself, organized by category.
- `src/verity/checks.py` — deterministic detectors (`scan_*`/`check_*` functions).
- `src/verity/metrics/deepeval_metrics.py` — semantic G-Eval detectors for paraphrase-resistant
  variants of the same risks.
- `tests/adversarial/test_redteam_hermetic.py` — the defense-to-check dispatch table
  (`_evaluate_probe`) that ties a probe's `defense` field to the actual assertion run against it.
- `docs/seeded-defects.md` — the 8 intentionally seeded defects this framework is built to catch,
  several of which map directly to rows in the table above.
