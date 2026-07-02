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
import hashlib
import json
import logging
import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

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


def hash_identifier(value: str) -> str:
    """Return a short, stable, non-reversible hash for a raw identifier.

    Used to redact member IDs (and similar identifiers) before they're
    attached to exported trace spans, which may be visible to a wider
    audience than the request itself (observability backends, log
    aggregators). The hash is deterministic within a run so spans for the
    same member can still be correlated without exposing the raw ID.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


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


def trace_id_hex(span: Any) -> str:
    """Return the 32-hex-char trace id of a span yielded by traced(), or "" if absent."""
    if span is None:
        return ""
    return format(span.context.trace_id, "032x")


def record_call_span(call_record: CallRecord) -> None:
    """Add model/token/cost attributes from a CallRecord to the current span."""
    if not _ENABLED:
        return

    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if not span.is_recording():
            return
        attrs = dict(getattr(span, "attributes", {}) or {})
        input_tokens = int(attrs.get("gen_ai.usage.input_tokens", 0))
        output_tokens = int(attrs.get("gen_ai.usage.output_tokens", 0))
        total_tokens = int(attrs.get("gen_ai.usage.total_tokens", 0))
        cost_usd = float(attrs.get("gen_ai.usage.cost_usd", 0.0))

        span.set_attribute("gen_ai.request.model", call_record.model)
        span.set_attribute("gen_ai.operation.name", call_record.label)
        span.set_attribute(
            "gen_ai.usage.input_tokens",
            input_tokens + call_record.usage.prompt_tokens,
        )
        span.set_attribute(
            "gen_ai.usage.output_tokens",
            output_tokens + call_record.usage.completion_tokens,
        )
        span.set_attribute(
            "gen_ai.usage.total_tokens",
            total_tokens + call_record.usage.total_tokens,
        )
        span.set_attribute("gen_ai.usage.cost_usd", cost_usd + call_record.cost.total_usd)
    except Exception as exc:
        logger.debug("Failed to set span attributes on call record: %s", exc)


@contextlib.contextmanager
def noop_span() -> Generator[None, None, None]:
    yield
