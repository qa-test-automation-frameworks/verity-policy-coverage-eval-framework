# Gemini hosted inference with a zero-spend constraint

## Selected path, checked 2026-10-18

Use **Google Gemini API Standard inference**, initially `gemini-3.8-flash`,
through Verity's existing Google/LiteLLM adapter. Google's current pricing lists
free-tier text input/output for this model. The existing local key can list the
model, which advertises `generateContent`. This is a candidate for evaluation;
its judge quality still needs independent measurement. No inference runs locally.

| Option | Assessment | Disposition |
| --- | --- | --- |
| Gemini free-tier project | Existing adapter/key; selected text model has a free tier; owner must verify billing is disabled | Selected |
| OpenRouter explicit free models | Existing adapter and zero-price routing controls; actual trial returned HTTP 404 because account policy excludes free-model training | Not selected; do not change account privacy settings |
| Groq free plan | Hosted open models and free quotas, but access depends on account plan and a dedicated adapter needs validation | Alternative only |
| Hugging Face Inference Providers | Free-user monthly credits are small and subject to change | Not the baseline for repeatable zero-spend execution |

Sources: [Gemini pricing and data use](https://ai.google.dev/gemini-api/docs/pricing),
[Gemini billing](https://ai.google.dev/gemini-api/docs/billing),
[Gemini model catalogue](https://ai.google.dev/api/models),
[OpenRouter free routes](https://openrouter.ai/docs/guides/routing/model-variants/free),
[Groq free-plan limits](https://console.groq.com/docs/rate-limits),
[Hugging Face credits](https://huggingface.co/docs/inference-providers/pricing).

## Required account state

Inspect the project associated with the local key in
[Google AI Studio's API key page](https://aistudio.google.com/api-keys). It must
show **Free**, with billing disabled. Free model availability and a valid key
alone do not establish the project's billing tier. The model endpoint does not
return billing status; this tool records an operator attestation rather than
pretending to verify billing through that endpoint.

Do not enable billing, attach a paid key, upgrade the project or purchase credits
to complete this experiment. A budget alert or project spend cap is not an
adequate substitute for disabled billing: Google's billing documentation notes
that project caps may permit overages. Free-tier data-use terms may allow Google
to improve its products using submitted content. This smoke sends only public,
fictional repository tuning examples; no personal or confidential data.

The owner confirmed in the implementation session that the existing key's
project is Free tier with billing disabled. Recheck before future studies or
when changing keys/projects. That attestation is not independent billing evidence.

## Commands

From the repository root after installing dependencies, configure only a local
`VERITY_GOOGLE_API_KEY`, `GOOGLE_API_KEY` or `GEMINI_API_KEY` in `.env` or the
process environment. Never put the key in command arguments or commit it.

```bash
# Authenticated model metadata only; no generation request.
make calibrate-free-check

# Recheck that THIS key's project is Free and has billing disabled first.
make calibrate-free-smoke FREE_ARGS=--confirm-free-project

# Smaller one-call check, or a separate local credential file:
PYTHONPATH=src:. uv run python scripts/run_free_hosted_calibration.py \
  --live --confirm-free-project --max-calls 1 --env-file /path/to/local/.env
```

The live command refuses to send even a metadata request without
`--confirm-free-project`. It permits only the reviewed model identifier, rejects
mutable `latest` aliases, checks current availability before inference, and never
substitutes another model. Pricing was reviewed on the date above; model metadata
contains capabilities, not current billing rates. Recheck the linked pricing
page and account limits before a new frozen evaluation plan.

## Limits and evidence

The runner builds a Google-only configuration, overriding ambient paid models,
alternate endpoints, judge providers, retries, cassette replay and secondary
credentials. It uses Standard `generateContent`, without Search/Maps grounding,
code execution, tools, explicit caching or paid fallback. SDK retries are zero.
A 401/403/429, provider outage, invalid score, missing usage, truncation or
nonzero cost if supplied stops the run and retains prior attempts.

Default bounds: seven calls at most; 2,048 output tokens per call and 14,336 per
run; 16,000 input UTF-8 bytes per call; 45-second timeout; at least 12.1 seconds
between calls. The pacing floor reflects the latest observed 5-RPM limit for the
selected free project; check the model's current quota before every run and use
a longer interval if its current limit is lower. Calls from other keys in the
same project share quota and can still cause a 429. Smaller remaining output
budgets reduce the next request's `max_tokens`. Actual input/output token use is
recorded; the input bound is
explicitly bytes, not an asserted exact token count. No local proxy can enforce
a zero-dollar invoice on a paid Gemini project; disabled billing is the control.

Receipts in ignored `reports/free-hosted/smoke-*.json` contain source revision and
dirty state, implementation/dataset/prompt hashes, catalogue snapshot and time,
operator attestation, limits, model/response IDs, token usage, timing, output and
each attempt's status. Persist only provider exception type/status to avoid
leaking credentials from error messages. Failed output is never converted to a
zero score or a passing control. Receipts do not overwrite historical reports
or authored cassettes.

Source checkouts resolve the revision and tracked-file dirty state from Git. The
distroless image has no Git executable; CI supplies the checked-out SHA through
the `VERITY_SOURCE_SHA` build argument. If neither source is available, live
mode stops before network access instead of producing an untraceable evaluation;
the receipt records unavailable source and unknown dirty state explicitly.

The generic static cost estimator remains unpriced for this model. A null
`provider_reported_cost_usd` means unreported, not measured zero; the zero-spend
claim relies on the confirmed free account and current published terms. A
stable API identifier is not a cryptographically pinned weights revision.

## D05 completion boundary

The smoke selects the first existing tuning case for each metric, in metric-name
order. Those labels/cassettes are authored/synthetic. Successful live smoke proves
connectivity and score parsing under the stated limits, not independent judge
agreement or permission to promote a metric.

For D05, follow the [held-out review protocol](calibration-review-workflow.md):
freeze a genuinely new split and analysis plan, obtain and lock at least two
independent reviewers' labels, record provider/model/bounds, then execute and
analyze the frozen study without tuning on held-out results. Hosted free-tier
integration removes a tooling dependency; human labeling and actual independent
study evidence remain prerequisites for verification.

## Observed smoke results

[Receipts and checksums](evidence/free-hosted-2026-10-18/index.json) preserve both
Gemini runs. The initial one-call check succeeded while the implementation was
uncommitted (the receipt records the dirty state and file hashes). The subsequent
batch ran on clean source `4c5aa328c49d2b1329914e2ed1c63c07b0a4fd05`:
its first score succeeded, then its second call returned HTTP 503. The batch
stopped without retry or fallback and is **failed/incomplete**, not seven passes.
There are two successful scored responses across the two runs; no live accuracy,
independent agreement or measured invoice amount is inferred from them. This
observed outage is also a practical limitation of depending on free hosted
capacity. Future runs must retain these outcomes rather than replacing them.
