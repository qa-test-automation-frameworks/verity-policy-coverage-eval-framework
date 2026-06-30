"""Unit tests for verity.tracing — always run with VERITY_TRACING unset (no-op path)."""

from __future__ import annotations

import os

import pytest

# Ensure tracing module is imported with VERITY_TRACING disabled
os.environ.setdefault("VERITY_TRACING", "0")


def test_traced_noop_when_disabled() -> None:
    """traced() must be a no-op when VERITY_TRACING is off."""
    from verity.tracing import traced

    entered = False
    with traced("test.span", key="value") as span:
        entered = True
        assert span is None
    assert entered


def test_init_tracing_noop_when_disabled() -> None:
    """init_tracing must not raise and must leave _TRACER as None when disabled."""
    from verity import tracing

    tracing._TRACER = None
    tracing._ENABLED = False
    tracing.init_tracing("test-service")
    assert tracing._TRACER is None


def test_record_call_span_noop_when_disabled() -> None:
    """record_call_span must not raise when tracing is disabled."""
    from verity import tracing
    from verity.cost import CallRecord, Cost, Usage

    tracing._ENABLED = False

    record = CallRecord(
        model="fake",
        label="test",
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        cost=Cost(prompt_usd=0.0, completion_usd=0.0, total_usd=0.001),
        latency_ms=0.0,
    )
    tracing.record_call_span(record)  # must not raise


def test_traced_enabled_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """traced() opens a real span when tracing is enabled (in-memory exporter)."""
    pytest.importorskip("opentelemetry.sdk")

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from verity import tracing

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    monkeypatch.setattr(tracing, "_ENABLED", True)
    monkeypatch.setattr(tracing, "_TRACER", tracer)

    with tracing.traced("my.operation", foo="bar") as span:
        assert span is not None

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "my.operation"
    assert spans[0].attributes["foo"] == "bar"


def test_record_call_span_sets_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    """record_call_span sets model/token/cost attributes on the current span."""
    pytest.importorskip("opentelemetry.sdk")


    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from verity import tracing

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    monkeypatch.setattr(tracing, "_ENABLED", True)
    monkeypatch.setattr(tracing, "_TRACER", tracer)

    from verity.cost import CallRecord, Cost, Usage

    record = CallRecord(
        model="openai/glm-5.2",
        label="agent-first-turn",
        usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        cost=Cost(prompt_usd=0.001, completion_usd=0.0005, total_usd=0.0015),
        latency_ms=250.0,
    )

    with tracer.start_as_current_span("outer"):
        tracing.record_call_span(record)

    spans = exporter.get_finished_spans()
    outer = next(s for s in spans if s.name == "outer")
    assert outer.attributes["llm.model"] == "openai/glm-5.2"
    assert outer.attributes["llm.total_tokens"] == 150
    assert outer.attributes["llm.cost_usd"] == pytest.approx(0.0015)
