# Observability & Cost Accounting

This document describes the tracing and cost-reporting capabilities added in M6.

---

## Architecture

```
agent.answer()          ← top-level span
  retrieval             ← child span (chunk_count via top_k attr)
  provider call         ← attributes on current span (model, tokens, cost)
  tool.coverage_calc    ← child span for tool execution (when called)
```

All instrumentation is gated on the `VERITY_TRACING` environment variable and
uses no-op stubs when disabled. The base install does not require the `otel` extra
— tracing adds zero overhead unless opted in.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VERITY_TRACING` | `0` | Set to `1` to enable OpenTelemetry span collection |
| `VERITY_TRACE_EXPORTER` | `file` | Comma-separated exporters: `console`, `file`, `otlp` |
| `VERITY_TRACE_DIR` | `reports/traces` | Directory for file-exporter JSONL output |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | — | gRPC endpoint for OTLP exporter (e.g. `http://localhost:4317`) |

Add these to `.env` when running locally with tracing enabled.

---

## Span Structure

Each `agent.answer()` call produces one trace with the following spans:

| Span Name | Attributes | Notes |
|-----------|-----------|-------|
| `agent.answer` | `member_id`, `query_len`, `gen_ai.request.model`, `gen_ai.operation.name`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.total_tokens`, `gen_ai.usage.cost_usd` | Top-level; LLM attributes set by `record_call_span()` |
| `retrieval` | `top_k` | Child of `agent.answer`; encloses retriever call |
| `tool.coverage_calculator` | — | Child of `agent.answer`; only present on tool-use paths |

If a response requests tool use, the agent may make additional provider calls
within its configured round and call budgets. Repeated `record_call_span()` calls
sum token and cost fields on the `agent.answer` span.

---

## Running the Trace Demo

```bash
make trace-demo
# or with custom exporter:
VERITY_TRACING=1 VERITY_TRACE_EXPORTER=console PYTHONPATH=src uv run python scripts/trace_demo.py
```

Spans are written to `reports/traces/spans-<timestamp>.jsonl` (one JSON object per line).
Each line includes name, trace_id, span_id, start_ns, end_ns, attributes, and status.

A real example, generated hermetically (cassette replay, no API key) and committed at
[`docs/samples/sample-trace.jsonl`](samples/sample-trace.jsonl), so the span shape and
`gen_ai.*` attributes are visible without running the demo first:

```json
{"name": "retrieval", "trace_id": "f9dd04fae71243a004af403f5ed5b08c", "span_id": "e7c5c8dfd0611af0", "start_ns": 1782995718788599931, "end_ns": 1782995718789313667, "attributes": {"top_k": 0}, "status": "UNSET"}
{"name": "agent.answer", "trace_id": "f9dd04fae71243a004af403f5ed5b08c", "span_id": "bf7832c05452c2c6", "start_ns": 1782995718785514820, "end_ns": 1782995718790087910, "attributes": {"member_id_hash": "5757dbffa1fefe96", "query_len": 34, "gen_ai.request.model": "openai/glm-4.5", "gen_ai.operation.name": "agent-first-turn", "gen_ai.usage.input_tokens": 130, "gen_ai.usage.output_tokens": 58, "gen_ai.usage.total_tokens": 188, "gen_ai.usage.cost_usd": 0.0002056}, "status": "UNSET"}
```

### Identifier redaction

`agent.answer` traces `member_id_hash` (a truncated SHA-256 of the raw member ID via
`verity.tracing.hash_identifier`), not the raw member ID. Spans and their exports may reach
a wider audience than the request itself (observability backends, log aggregators), so the
raw identifier never leaves the process on this path. The hash is deterministic within a
process, so spans for the same member can still be correlated across a trace without
exposing the identifier itself.

---

## Per-Run Cost Summary

`verity.reporting.render_cost_summary(accumulator)` produces a markdown table
breaking down LLM calls by label (`agent-first-turn`, `agent-second-turn`, `judge`, etc.)
with prompt tokens, completion tokens, total tokens, and estimated USD cost.

`write_step_summary(text)` appends the table to `$GITHUB_STEP_SUMMARY` in CI
(visible in the GitHub Actions job summary) or to `reports/cost-summary-local.md` locally.

The semantic (`tests/semantic/`) and adversarial (`tests/adversarial/`) suites
both wire a shared session accumulator and call `write_step_summary` on session finish.
Even hermetic (cassette replay) runs produce the cost table, since recorded token
counts are replayed through `RunAccumulator`.

### Semantic request and token ledger

Semantic runs share one accumulator between the SUT and judge. At session end the
framework prints suite totals and a per-test breakdown, with SUT and judge request
counts and token totals. `VERITY_SEMANTIC_VERBOSITY=verbose` also prints each
sanitized request row; `quiet` prints only suite totals. The full machine-readable
ledger is always written to `reports/semantic/usage.json` locally and included in
the `semantic-eval-reports` or `semantic-smoke-reports` Actions artifact. The
`reports/semantic/results.json` manifest points to it and includes request totals.
Download the artifact from the workflow run to compare past runs, subject to the
repository's Actions artifact-retention policy.

Each row contains a generated request ID, pytest node ID, model, label, source,
status, latency, provider-reported prompt/completion/total tokens, and an estimated
cost when a verified price is available. Failed attempts retain only the exception
class and HTTP status. Prompts, credentials, and headers are not stored in this
ledger. Missing provider usage is explicitly marked unavailable instead of inferred
as a token count. Costs remain estimates from the reference price table, not billing data.

When a live semantic workflow is run with `verbosity=verbose`, it also uploads a
separate `semantic-case-evidence` artifact for 30 days. Its `case-evidence.jsonl`
records each final SUT answer, case query and expected behavior, retrieved chunk text
and provenance, tool arguments/results, answer citations, token counts, and the judge
response text, score/rationale, or parsing error when available. Credential-shaped
values are redacted before writing. Truncated judge output gets one larger-token retry;
syntactically invalid JSON gets one correction retry. A valid JSON object with missing
metric-specific fields remains a failed evaluation rather than having verdicts inferred.
This trace is intended for the synthetic golden dataset; treat it as
potentially sensitive because model answers can repeat information from their input.
Standard and quiet runs do not retain answer text. The separate short-retention artifact
keeps raw answers out of durable trend and portfolio evidence records.
To inspect it, open the semantic workflow run in GitHub Actions and download the
`semantic-case-evidence` artifact; each JSONL row is a SUT response, judge response,
judge result, or verbosity-mode marker, keyed by test ID/case ID where applicable.

The ledger counts each framework-level LiteLLM submission, including the secondary
credential attempt when fallback is used. NVIDIA NIM calls are limited to 40 starts in any
rolling 60-second window across the shared SUT/judge accumulator; each ledger row records
the time spent waiting for a slot. NIM SDK retries are disabled so one ledger row represents
one attempted NIM request. `VERITY_RETRIES` defaults to `0`, and semantic settings explicitly
set it to `0` even when a developer `.env` overrides the default. Semantic runs share a
circuit breaker across SUT and judge calls; after five recorded HTTP 429 responses, the
current test is allowed to finish and pytest stops before starting another test. Cassette
replay rows are marked `source: cassette` and represent no live API call. For non-NIM
providers, explicitly enabled LiteLLM/SDK retries are not individually exposed and may make
upstream request counts higher than ledger counts.

### Hermetic replay note

Committed local report artifacts generated from cassette replay are useful for token and cost accounting, but replay latency is not representative of live provider latency.

---

## Installing the OTel Extra

The base install does not include OpenTelemetry packages. To install them:

```bash
uv sync --extra otel
# or with pip:
pip install "verity-policy-coverage-eval-framework[otel]"
```

For OTLP export (e.g. to Phoenix or a local collector):

```bash
VERITY_TRACING=1 VERITY_TRACE_EXPORTER=otlp \
  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
  make eval-semantic
```

---

## CI Integration

The `adversarial.yml` workflow runs the hermetic suite on every execution and
the cost table appears in the GitHub Actions job summary automatically.
When the provider API key matching `VERITY_PROVIDER` is set, the live calibration and Promptfoo runs
also contribute to the cost summary via the same reporting hooks.
