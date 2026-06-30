# Observability & Cost Accounting

This document describes the tracing and cost-reporting capabilities added in M6.

---

## Architecture

```
agent.answer()          ← top-level span
  retrieval             ← child span (chunk_count via top_k attr)
  llm.generate          ← attributes on current span (model, tokens, cost)
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
| `agent.answer` | `member_id`, `query_len`, `llm.model`, `llm.label`, `llm.prompt_tokens`, `llm.completion_tokens`, `llm.total_tokens`, `llm.cost_usd` | Top-level; LLM attributes set by `record_call_span()` |
| `retrieval` | `top_k` | Child of `agent.answer`; encloses retriever call |
| `tool.coverage_calculator` | — | Child of `agent.answer`; only present on tool-use paths |

If two LLM calls occur (first turn + second turn after tool use), both
`record_call_span()` calls annotate the `agent.answer` span with the
second call's attributes (last-write wins for repeated keys).

---

## Running the Trace Demo

```bash
make trace-demo
# or with custom exporter:
VERITY_TRACING=1 VERITY_TRACE_EXPORTER=console PYTHONPATH=src uv run python scripts/trace_demo.py
```

Spans are written to `reports/traces/spans-<timestamp>.jsonl` (one JSON object per line).
Each line includes name, trace_id, span_id, start_ns, end_ns, attributes, and status.

---

## Per-Run Cost Summary

`verity.reporting.render_cost_summary(accumulator)` produces a markdown table
breaking down LLM calls by label (`agent-first-turn`, `agent-second-turn`, `judge`, etc.)
with prompt tokens, completion tokens, total tokens, and estimated USD cost.

`write_step_summary(text)` appends the table to `$GITHUB_STEP_SUMMARY` in CI
(visible in the GitHub Actions job summary) or to `reports/cost-summary.md` locally.

The semantic (`tests/semantic/`) and adversarial (`tests/adversarial/`) suites
both wire a shared session accumulator and call `write_step_summary` on session finish.
Even hermetic (cassette replay) runs produce the cost table, since recorded token
counts are replayed through `RunAccumulator`.

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
When `VERITY_ZAI_API_KEY` is set, the live calibration and Promptfoo runs
also contribute to the cost summary via the same reporting hooks.
