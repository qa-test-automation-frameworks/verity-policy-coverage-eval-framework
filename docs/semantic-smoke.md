# Semantic smoke suite

The manual **Semantic Eval** workflow defaults to `suite=smoke`. It runs a curated,
serial, one-sample subset and stops at the first failure (`pytest -x`). The `full`
choice runs the complete semantic suite; push and scheduled runs remain full-suite runs.

The smoke selection contains 12 test cases:

- One fixed G-Eval completeness canary runs first to check whether the judge can return
  parseable scoring output before spending calls on the system under test.
- Clean and seeded-defect examples cover completeness, faithfulness, and task completion.
- Seeded-defect examples cover disambiguation, refusal, prompt-injection compliance, and
  PII leakage; a clean answer-relevancy example provides another control.

Choose `provider` and `model` for the system under test. `judge_provider=same` retains
same-provider judging; choosing a provider such as `google` requires an explicit
`judge_model`. A same-provider judge model defaults to the selected system-under-test
model unless `judge_model` overrides it. The judge provider must have its own Actions
secret when it differs from the system-under-test provider.

The suite uses one sample per case and runs sequentially. Its provider-request count is
not a hard cap: the agent may make several calls for a tool-using answer, and provider
retries can add calls. The preflight and fail-fast setting avoid running the rest of the
suite when judge formatting is already incompatible. A smoke pass is a quick compatibility
signal, not a statistically powered quality or calibration result; use the full suite and
independent human labels for those conclusions. Smoke reports use a separate Actions
artifact (`semantic-smoke-reports`) and evidence scope (`verity.semantic-smoke`), so they
do not replace the full-suite report or `verity.semantic-evaluation` record used by the
portfolio.

Judge calls request JSON mode through the provider API. NVIDIA judge calls also disable
Nemotron thinking for the JSON response so reasoning tokens do not consume the output
budget first. An empty judge response fails with a diagnostic containing the model,
finish reason, and whether reasoning text was returned separately; response content is
not written to logs.
