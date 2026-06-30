"""OpenTelemetry span helpers with a no-op fallback.

When VERITY_TRACING is not set (or set to "0"/"false"), all span operations
are no-ops — zero cost, no import of opentelemetry packages required. This
keeps Tier-1 hermetic tests fast and the base install lean.

When VERITY_TRACING=1, this module initialises an SDK TracerProvider with
the exporters requested via VERITY_TRACE_EXPORTER (comma-separated):
  console   — SpanExporter writing JSON lines to stderr
  file      — SpanExporter writing JSON to reports/traces/spans-<timestamp>.jsonl
  otlp      — gRPC OtlpSpanExporter (requires OTEL_EXPORTER_OTLP_ENDPOINT)

Usage:
    from verity.tracing import traced, record_call_span

    with traced("retrieval", chunk_count=4):
        chunks = retriever.retrieve(query)

    record_call_span(call_record)   # attaches model/tokens/cost to current span
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from verity.cost import CallRecord

_ENABLED: bool = os.environ.get("VERITY_TRACING", "0").lower() not in ("0", "false", "")
_TRACER: Any = None


def _init_file_exporter(export_dir: Path) -> Any:
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

    export_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    path = export_dir / f"spans-{ts}.jsonl"

    class _FileExporter(SpanExporter):
        def export(self, spans: Any) -> Any:
            with path.open("a") as fh:
                for span in spans:
                    fh.write(json.dumps(_span_to_dict(span)) + "\n")
            return SpanExportResult.SUCCESS

        def shutdown(self) -> None:
            pass

    return _FileExporter()


def _span_to_dict(span: Any) -> dict[str, Any]:
    attrs = dict(span.attributes or {})
    return {
        "name": span.name,
        "trace_id": format(span.context.trace_id, "032x"),
        "span_id": format(span.context.span_id, "016x"),
        "start_ns": span.start_time,
        "end_ns": span.end_time,
        "attributes": attrs,
        "status": span.status.status_code.name if span.status else "UNSET",
    }


def init_tracing(service_name: str = "verity") -> None:
    """Initialise the SDK TracerProvider (called once at process start)."""
    global _TRACER
    if not _ENABLED:
        return

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    exporters_env = os.environ.get("VERITY_TRACE_EXPORTER", "file")
    for name in [e.strip() for e in exporters_env.split(",") if e.strip()]:
        if name == "console":
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        elif name == "file":
            export_dir = Path(os.environ.get("VERITY_TRACE_DIR", "reports/traces"))
            provider.add_span_processor(BatchSpanProcessor(_init_file_exporter(export_dir)))
        elif name == "otlp":
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )
                provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
            except ImportError:
                print(
                    "Warning: otlp exporter requested but opentelemetry-exporter-otlp-proto-grpc "
                    "is not installed. Install with: uv sync --extra otel",
                    file=sys.stderr,
                )

    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer(service_name)


def get_tracer() -> Any:
    return _TRACER


@contextmanager
def traced(name: str, **attributes: Any) -> Generator[Any, None, None]:
    """Context manager that opens a span when tracing is enabled, no-op otherwise."""
    if not _ENABLED or _TRACER is None:
        yield None
        return

    with _TRACER.start_as_current_span(name) as span:
        for k, v in attributes.items():
            span.set_attribute(k, v)
        yield span


def record_call_span(call_record: CallRecord) -> None:
    """Add model/token/cost attributes from a CallRecord to the current span."""
    if not _ENABLED:
        return

    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if not span.is_recording():
            return
        span.set_attribute("llm.model", call_record.model)
        span.set_attribute("llm.label", call_record.label)
        span.set_attribute("llm.prompt_tokens", call_record.usage.prompt_tokens)
        span.set_attribute("llm.completion_tokens", call_record.usage.completion_tokens)
        span.set_attribute("llm.total_tokens", call_record.usage.total_tokens)
        span.set_attribute("llm.cost_usd", call_record.cost.total_usd)
    except Exception:
        pass


@contextlib.contextmanager
def noop_span() -> Generator[None, None, None]:
    yield
