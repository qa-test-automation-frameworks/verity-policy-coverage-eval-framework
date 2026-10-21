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


def _tool_call_result(
    args_json: str = '{"claim_amount": 500.0}', *, call_id: str = "call_test_001"
) -> CompletionResult:
    tc = ReplayToolCall(
        id=call_id,
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

    def test_empty_final_completion_returns_safe_failure(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        provider = MagicMock()
        provider.accumulator = accumulator
        provider.complete.return_value = CompletionResult(content="  \n", tool_calls=[])
        agent = CoverageAgent(settings=settings, retriever=retriever, provider=provider)

        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        _assert_safe_failure(response, "empty_final_answer")

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


class TestBoundedMultiRoundToolCalls:
    """Tool requests can continue across rounds but remain strictly bounded."""

    def test_second_round_of_tool_calls_executes_and_finalizes(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        first_args = (
            '{"claim_amount": 1000.0, "plan_deductible": 750.0, "accrued_deductible": 750.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 1200.0, "coinsurance_member": 0.10}'
        )
        second_args = (
            '{"claim_amount": 500.0, "plan_deductible": 750.0, "accrued_deductible": 500.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 1200.0, "coinsurance_member": 0.10}'
        )
        call_count: list[int] = [0]
        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator

        def _complete(**kwargs: Any) -> CompletionResult:
            call_count[0] += 1
            if call_count[0] == 1:
                return _tool_call_result(first_args)
            if call_count[0] == 2:
                return _tool_call_result(second_args, call_id="call_test_002")
            return CompletionResult(content="The final answer uses both calculations.")

        mock_provider.complete.side_effect = _complete
        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)

        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        assert call_count[0] == 3
        assert response.answer == "The final answer uses both calculations."
        assert len(response.tool_invocations) == 2
        assert [call.tool_name for call in response.tool_invocations] == [
            "coverage_calculator",
            "coverage_calculator",
        ]
        # Every follow-up keeps the tool schema available and includes the
        # complete assistant/tool conversation history.
        for call_args in mock_provider.complete.call_args_list[1:]:
            assert call_args.kwargs["tools"]
            assert call_args.kwargs["messages"][-1]["role"] == "tool"

    def test_round_limit_returns_safe_failure(self) -> None:
        settings = _make_settings().model_copy(update={"max_tool_rounds": 1})
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")
        args_json = (
            '{"claim_amount": 1000.0, "plan_deductible": 750.0, "accrued_deductible": 750.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 1200.0, "coinsurance_member": 0.10}'
        )
        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        mock_provider.complete.side_effect = [
            _tool_call_result(args_json),
            _tool_call_result(args_json, call_id="call_test_002"),
        ]
        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)

        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        assert mock_provider.complete.call_count == 2
        _assert_safe_failure(response, "tool_round_limit")
        assert len(response.tool_invocations) == 1

    def test_total_tool_call_limit_rejects_oversized_batch(self) -> None:
        settings = _make_settings().model_copy(update={"max_tool_calls": 1})
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")
        args_json = (
            '{"claim_amount": 500.0, "plan_deductible": 750.0, "accrued_deductible": 500.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 0.0, "coinsurance_member": 0.10}'
        )
        first = _tool_call_result(args_json).tool_calls[0]
        second = _tool_call_result(args_json, call_id="call_test_002").tool_calls[0]
        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        mock_provider.complete.return_value = CompletionResult(
            content="", tool_calls=[first, second]
        )
        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)

        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        mock_provider.complete.assert_called_once()
        _assert_safe_failure(response, "tool_call_limit")
        assert response.tool_invocations == []

    def test_repeated_tool_call_reuses_result_for_final_synthesis(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")
        args_json = (
            '{"claim_amount": 500.0, "plan_deductible": 750.0, "accrued_deductible": 500.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 0.0, "coinsurance_member": 0.10}'
        )
        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        mock_provider.complete.side_effect = [
            _tool_call_result(args_json),
            _tool_call_result(args_json, call_id="call_test_002"),
            CompletionResult(content="You owe $275: $250 to the deductible and $25 coinsurance."),
        ]
        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)

        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        assert mock_provider.complete.call_count == 3
        assert response.answer == "You owe $275: $250 to the deductible and $25 coinsurance."
        assert not response.refused
        assert len(response.tool_invocations) == 1
        recovery_call = mock_provider.complete.call_args_list[2].kwargs
        assert "tools" not in recovery_call
        assert recovery_call["label"] == "agent-repeat-recovery"
        assert recovery_call["messages"][-1]["role"] == "user"
        assert "Do not call a tool again" in recovery_call["messages"][-1]["content"]

    def test_repeat_recovery_fails_closed_if_model_requests_another_tool(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")
        args_json = (
            '{"claim_amount": 500.0, "plan_deductible": 750.0, "accrued_deductible": 500.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 0.0, "coinsurance_member": 0.10}'
        )
        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        mock_provider.complete.side_effect = [
            _tool_call_result(args_json),
            _tool_call_result(args_json, call_id="call_test_002"),
            _tool_call_result(args_json, call_id="call_test_003"),
        ]
        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)

        response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

        assert mock_provider.complete.call_count == 3
        _assert_safe_failure(response, "tool_loop_detected")
        assert len(response.tool_invocations) == 1


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

        _assert_safe_failure(response, "invalid_tool_arguments")

    def test_schema_invalid_tool_arguments_are_classified_without_logging_values(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        mock_provider.complete.return_value = _tool_call_result(
            '{"claim_amount": 0, "plan_deductible": 750.0, "accrued_deductible": 0.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 0.0, "coinsurance_member": 0.10}'
        )

        agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)
        response = agent.answer("Compare my urgent-care copays.", member_id="MBR-003")

        _assert_safe_failure(response, "invalid_tool_arguments")
        assert "greater_than" in caplog.text
        assert "input_value=0" not in caplog.text

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

        _assert_safe_failure(response, "invalid_tool_arguments")


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
