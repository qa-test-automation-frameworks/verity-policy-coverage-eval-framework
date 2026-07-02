"""Unit tests for verity.tracing — always run with VERITY_TRACING unset (no-op path)."""

from __future__ import annotations

import os

import pytest

# Ensure tracing module is imported with VERITY_TRACING disabled
os.environ.setdefault("VERITY_TRACING", "0")


def test_hash_identifier_is_deterministic_and_not_reversible() -> None:
    from verity.tracing import hash_identifier

    h1 = hash_identifier("MBR-001")
    h2 = hash_identifier("MBR-001")
    assert h1 == h2
    assert "MBR-001" not in h1
    assert h1 != hash_identifier("MBR-002")


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


def test_agent_answer_span_excludes_raw_member_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """agent.answer's span must carry a hashed member_id, never the raw one."""
    pytest.importorskip("opentelemetry.sdk")

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from sut.agent import CoverageAgent
    from sut.retriever import FixtureRetriever
    from verity import tracing
    from verity.cassettes import CassetteLibrary
    from verity.config import Provider, Settings
    from verity.providers import LLMProvider

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    monkeypatch.setattr(tracing, "_ENABLED", True)
    monkeypatch.setattr(tracing, "_TRACER", tracer)

    settings = Settings(
        _env_file=None,
        provider=Provider.zai,
        model="glm-4.5",
        cassette_mode="replay",
        cassette_dir="datasets/cassettes",
    )
    lib = CassetteLibrary(settings.cassette_dir)
    llm_provider = LLMProvider(settings, cassette_library=lib)
    retriever = FixtureRetriever("defect-7-prompt-injection")
    agent = CoverageAgent(settings=settings, retriever=retriever, provider=llm_provider)

    agent.answer("What does my policy cover overall?", member_id="MBR-001")

    answer_spans = [s for s in exporter.get_finished_spans() if s.name == "agent.answer"]
    assert answer_spans
    attrs = answer_spans[0].attributes
    assert "member_id" not in attrs
    assert attrs["member_id_hash"] == tracing.hash_identifier("MBR-001")
    assert "MBR-001" not in str(attrs.values())


def test_trace_id_hex_returns_empty_string_for_no_span() -> None:
    from verity.tracing import trace_id_hex

    assert trace_id_hex(None) == ""


def test_trace_id_hex_matches_span_context(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("opentelemetry.sdk")

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from verity import tracing
    from verity.tracing import trace_id_hex

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    monkeypatch.setattr(tracing, "_ENABLED", True)
    monkeypatch.setattr(tracing, "_TRACER", tracer)

    with tracing.traced("my.operation") as span:
        hex_id = trace_id_hex(span)
        assert len(hex_id) == 32
        assert hex_id == format(span.context.trace_id, "032x")


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
        model="openai/glm-4.5",
        label="agent-first-turn",
        usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        cost=Cost(prompt_usd=0.001, completion_usd=0.0005, total_usd=0.0015),
        latency_ms=250.0,
    )

    with tracer.start_as_current_span("outer"):
        tracing.record_call_span(record)

    spans = exporter.get_finished_spans()
    outer = next(s for s in spans if s.name == "outer")
    assert outer.attributes["gen_ai.request.model"] == "openai/glm-4.5"
    assert outer.attributes["gen_ai.usage.total_tokens"] == 150
    assert outer.attributes["gen_ai.usage.cost_usd"] == pytest.approx(0.0015)


def test_record_call_span_accumulates_usage_on_current_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """record_call_span sums repeated usage fields on the active span."""
    pytest.importorskip("opentelemetry.sdk")

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from verity import tracing
    from verity.cost import CallRecord, Cost, Usage

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    monkeypatch.setattr(tracing, "_ENABLED", True)
    monkeypatch.setattr(tracing, "_TRACER", tracer)

    first = CallRecord(
        model="openai/glm-4.5",
        label="first",
        usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        cost=Cost(prompt_usd=0.001, completion_usd=0.0005, total_usd=0.0015),
        latency_ms=250.0,
    )
    second = CallRecord(
        model="openai/glm-4.5",
        label="second",
        usage=Usage(prompt_tokens=25, completion_tokens=10, total_tokens=35),
        cost=Cost(prompt_usd=0.00025, completion_usd=0.0001, total_usd=0.00035),
        latency_ms=100.0,
    )

    with tracer.start_as_current_span("outer"):
        tracing.record_call_span(first)
        tracing.record_call_span(second)

    outer = next(s for s in exporter.get_finished_spans() if s.name == "outer")
    assert outer.attributes["gen_ai.usage.input_tokens"] == 125
    assert outer.attributes["gen_ai.usage.output_tokens"] == 60
    assert outer.attributes["gen_ai.usage.total_tokens"] == 185
    assert outer.attributes["gen_ai.usage.cost_usd"] == pytest.approx(0.00185)


class TestInitTracing:
    def test_init_tracing_console_exporter_sets_tracer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("opentelemetry.sdk")
        from verity import tracing

        monkeypatch.setattr(tracing, "_ENABLED", True)
        monkeypatch.setattr(tracing, "_TRACER", None)
        monkeypatch.setenv("VERITY_TRACE_EXPORTER", "console")
        tracing.init_tracing("test-console-service")
        assert tracing.get_tracer() is not None

    def test_file_exporter_writes_span_file(self, tmp_path: object) -> None:
        """Exercise _init_file_exporter's export() directly — OTel only allows one
        global TracerProvider per process, so a second init_tracing() call in the
        same test session can't be reliably asserted through the SDK's own API."""
        pytest.importorskip("opentelemetry.sdk")
        from pathlib import Path

        from verity.tracing import _init_file_exporter

        trace_dir = Path(str(tmp_path)) / "traces"
        exporter = _init_file_exporter(trace_dir)

        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )

        capture = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(capture))
        tracer = provider.get_tracer("file-export-test")
        with tracer.start_as_current_span("file-export-test-span"):
            pass

        exporter.export(capture.get_finished_spans())
        exporter.shutdown()

        assert trace_dir.exists()
        span_files = list(trace_dir.glob("spans-*.jsonl"))
        assert span_files, "expected at least one spans-*.jsonl file to be written"
        content = span_files[0].read_text()
        assert "file-export-test-span" in content

    def test_init_tracing_noop_leaves_tracer_none_when_flag_off(self) -> None:
        from verity import tracing

        tracing._ENABLED = False
        tracing._TRACER = None
        tracing.init_tracing("unused")
        assert tracing.get_tracer() is None

    def test_init_tracing_unknown_exporter_name_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("opentelemetry.sdk")
        from verity import tracing

        monkeypatch.setattr(tracing, "_ENABLED", True)
        monkeypatch.setattr(tracing, "_TRACER", None)
        monkeypatch.setenv("VERITY_TRACE_EXPORTER", "nonexistent-exporter-name")
        tracing.init_tracing("test-unknown-exporter")
        # Tracer is still created even if the requested exporter name is unrecognized.
        assert tracing.get_tracer() is not None
