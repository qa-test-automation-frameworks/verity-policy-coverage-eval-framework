"""Tests for agent failure-mode paths.

Documents how CoverageAgent responds when downstream components fail:
- run_coverage_calculator raises during tool execution
- provider.complete raises on the second LLM turn (e.g. after a tool result)

These tests prove the current behavior (exceptions propagate uncaught), which
is a documented gap. The SUT's tool is read-only cost math, so no irreversible
action occurs on failure, but the agent does not degrade to a safe fallback
response — it raises.
"""

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
    """A CompletionResult that carries one coverage_calculator tool call."""
    tc = ReplayToolCall(
        id="call_test_001",
        function=ReplayFunction(name="coverage_calculator", arguments=args_json),
    )
    return CompletionResult(content="", tool_calls=[tc])


def _text_result(text: str = "Your coverage is as follows.") -> CompletionResult:
    return CompletionResult(content=text, tool_calls=[])


class TestToolExecutionFailure:
    """When run_coverage_calculator raises, the exception propagates from agent.answer()."""

    def test_tool_value_error_propagates(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        # First turn returns a tool call; tool then raises
        mock_provider.complete.return_value = _tool_call_result(
            '{"claim_amount": 500.0, "plan_deductible": 750.0, "accrued_deductible": 750.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 0.0, "coinsurance_member": 0.10}'
        )

        agent = CoverageAgent(
            settings=settings, retriever=retriever, provider=mock_provider
        )

        with (
            patch("sut.agent.run_coverage_calculator", side_effect=ValueError("bad input")),
            pytest.raises(ValueError, match="bad input"),
        ):
            agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

    def test_tool_runtime_error_propagates(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        mock_provider = MagicMock()
        mock_provider.accumulator = accumulator
        mock_provider.complete.return_value = _tool_call_result(
            '{"claim_amount": 1000.0, "plan_deductible": 750.0, "accrued_deductible": 0.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 0.0, "coinsurance_member": 0.10}'
        )

        agent = CoverageAgent(
            settings=settings, retriever=retriever, provider=mock_provider
        )

        exc = RuntimeError("calculator failed")
        with (
            patch("sut.agent.run_coverage_calculator", side_effect=exc),
            pytest.raises(RuntimeError, match="calculator failed"),
        ):
            agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")


class TestProviderSecondTurnFailure:
    """When provider.complete raises on the second LLM turn, the exception propagates."""

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

    def test_second_turn_connection_error_propagates(self) -> None:
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

        with pytest.raises(ConnectionError, match="provider unreachable"):
            agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")

    def test_second_turn_timeout_propagates(self) -> None:
        settings = _make_settings()
        accumulator = _no_op_accumulator()
        retriever = FixtureRetriever("ctrl-gold-deductible")

        args_json = (
            '{"claim_amount": 500.0, "plan_deductible": 750.0, "accrued_deductible": 200.0,'
            ' "plan_oop_max": 4000.0, "accrued_oop": 0.0, "coinsurance_member": 0.10}'
        )
        provider = self._make_failing_second_turn_provider(
            accumulator, TimeoutError("LLM call timed out"), args_json
        )
        agent = CoverageAgent(settings=settings, retriever=retriever, provider=provider)

        with pytest.raises(TimeoutError, match="LLM call timed out"):
            agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-003")
