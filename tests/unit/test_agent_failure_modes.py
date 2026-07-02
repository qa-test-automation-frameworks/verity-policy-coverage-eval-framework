"""Tests for structured agent failure responses."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from sut.agent import CoverageAgent
from sut.retriever import FixtureRetriever
from verity.cassettes import ReplayFunction, ReplayToolCall
from verity.config import Settings
from verity.cost import RunAccumulator
from verity.providers import CompletionResult


def _make_settings() -> Settings:
    return Settings(cassette_mode="off")


def _no_op_accumulator() -> RunAccumulator:
    return RunAccumulator()


def _tool_call_result(args_json: str = '{"claim_amount": 500.0}') -> CompletionResult:
    tc = ReplayToolCall(
        id="call_test_001",
        function=ReplayFunction(name="coverage_calculator", arguments=args_json),
    )
    return CompletionResult(content="", tool_calls=[tc])


def _assert_safe_failure(response: Any, category: str) -> None:
    assert response.refused
    assert response.requires_human_review
    assert response.refusal_reason == category
    assert response.failure_category == category
    # trace_id is populated from the active span's trace context; with
    # tracing disabled (the default here) there is no span, so it stays "".
    assert response.trace_id == ""
    assert "cannot complete this coverage response right now" in response.answer


class TestToolExecutionFailure:
    """Tool execution failures return a safe structured response."""

    def test_tool_value_error_returns_safe_response(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        mock_provider.complete.return_value = _tool_call_result(
            '{"claim_amount": 500.0, "plan_deductible": 750.0, "accrued_deductible": 750.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 0.0, "coinsurance_member": 0.10}'
        )

        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)

        with patch("sut.agent.run_coverage_calculator", side_effect=ValueError("bad input")):
            response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        _assert_safe_failure(response, "tool_unavailable")

    def test_tool_runtime_error_returns_safe_response(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        mock_provider.complete.return_value = _tool_call_result(
            '{"claim_amount": 1000.0, "plan_deductible": 750.0, "accrued_deductible": 0.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 0.0, "coinsurance_member": 0.10}'
        )

        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)

        with patch(
            "sut.agent.run_coverage_calculator",
            side_effect=RuntimeError("calculator failed"),
        ):
            response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        _assert_safe_failure(response, "tool_unavailable")


class TestProviderFailure:
    """Provider failures return safe structured responses."""

    def _make_failing_second_turn_provider(
        self,
        accumulator: RunAccumulator,
        exc: Exception,
        args_json: str,
    ) -> Any:
        call_count: list[int] = [0]
        mock = MagicMock()
        mock.accumulator = accumulator

        def _complete(**kwargs: Any) -> CompletionResult:
            call_count[0] += 1
            if call_count[0] == 1:
                return _tool_call_result(args_json)
            raise exc

        mock.complete.side_effect = _complete
        return mock

    def test_first_turn_connection_error_returns_safe_response(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        provider = MagicMock()
        provider.accumulator = accumulator
        provider.complete.side_effect = ConnectionError("provider unreachable")
        agent = CoverageAgent(settings=settings, retriever=retriever, provider=provider)

        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        _assert_safe_failure(response, "provider_unavailable")

    def test_second_turn_connection_error_returns_safe_response(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        args_json = (
            '{"claim_amount": 1000.0, "plan_deductible": 750.0, "accrued_deductible": 750.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 1200.0, "coinsurance_member": 0.10}'
        )
        provider = self._make_failing_second_turn_provider(
            accumulator, ConnectionError("provider unreachable"), args_json
        )
        agent = CoverageAgent(settings=settings, retriever=retriever, provider=provider)

        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        _assert_safe_failure(response, "provider_unavailable")

    def test_second_turn_timeout_returns_safe_response(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        args_json = (
            '{"claim_amount": 500.0, "plan_deductible": 750.0, "accrued_deductible": 200.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 0.0, "coinsurance_member": 0.10}'
        )
        provider = self._make_failing_second_turn_provider(
            accumulator, TimeoutError("call timed out"), args_json
        )
        agent = CoverageAgent(settings=settings, retriever=retriever, provider=provider)

        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        _assert_safe_failure(response, "provider_unavailable")


class TestSecondRoundToolCalls:
    """A second round of tool_calls in the post-tool response is rejected,
    not silently treated as the final answer."""

    def test_second_round_tool_calls_rejected(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        args_json = (
            '{"claim_amount": 1000.0, "plan_deductible": 750.0, "accrued_deductible": 750.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 1200.0, "coinsurance_member": 0.10}'
        )
        call_count: list[int] = [0]
        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator

        def _complete(**kwargs: Any) -> CompletionResult:
            call_count[0] += 1
            return _tool_call_result(args_json)

        mock_provider.complete.side_effect = _complete
        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)

        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        assert call_count[0] == 2
        _assert_safe_failure(response, "tool_unavailable")


class TestToolArgumentContracts:
    """Malformed or unrecognized tool calls return a safe structured response."""

    def test_unknown_tool_name_returns_safe_response(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        tc = ReplayToolCall(
            id="call_test_002",
            function=ReplayFunction(name="delete_member_record", arguments="{}"),
        )
        mock_provider.complete.return_value = CompletionResult(content="", tool_calls=[tc])

        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)
        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        _assert_safe_failure(response, "unknown_tool")

    def test_malformed_tool_arguments_returns_safe_response(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        mock_provider.complete.return_value = _tool_call_result(args_json="{not valid json")

        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)
        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        _assert_safe_failure(response, "tool_unavailable")

    def test_unexpected_tool_argument_returns_safe_response(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        mock_provider.complete.return_value = _tool_call_result(
            '{"claim_amount": 500.0, "plan_deductible": 750.0, "accrued_deductible": 200.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 0.0, "coinsurance_member": 0.10,'
            ' "unexpected_field": "sneaky"}'
        )

        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)
        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        _assert_safe_failure(response, "tool_unavailable")


class TestTraceIdCorrelation:
    """response.trace_id must match the trace id of the span emitted for the call."""

    def test_success_response_trace_id_matches_emitted_span(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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

        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")
        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        mock_provider.complete.return_value = CompletionResult(content="Answer.", tool_calls=[])

        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)
        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        emitted = next(s for s in exporter.get_finished_spans() if s.name == "agent.answer")
        assert response.trace_id == format(emitted.context.trace_id, "032x")

    def test_failure_response_trace_id_matches_emitted_span(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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

        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")
        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        mock_provider.complete.side_effect = ConnectionError("provider unreachable")

        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)
        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        emitted = next(s for s in exporter.get_finished_spans() if s.name == "agent.answer")
        assert response.refused
        assert response.trace_id == format(emitted.context.trace_id, "032x")
