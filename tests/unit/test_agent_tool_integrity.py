"""Proves the agent's tool messages always originate from its own
run_coverage_calculator() call — never from model-generated content
smuggled in as if it were a tool response."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from sut.agent import CoverageAgent
from sut.retriever import FixtureRetriever
from sut.tools.coverage_calculator import run_coverage_calculator
from verity.cassettes import ReplayFunction, ReplayToolCall
from verity.config import Settings
from verity.cost import RunAccumulator
from verity.providers import CompletionResult

_ARGS_JSON = (
    '{"claim_amount": 1000.0, "plan_deductible": 750.0, "accrued_deductible": 750.0,'
    ' "plan_oop_max": 4000.0, "accrued_oop": 1200.0, "coinsurance_member": 0.10}'
)


def test_second_turn_tool_messages_only_contain_orchestrator_results() -> None:
    """Every {"role": "tool", ...} message the agent sends on the second turn
    must have tool_call_id matching an id from the first turn's tool_calls,
    and content equal to json.dumps(run_coverage_calculator(args)) — never
    content derived from the model's own text."""
    settings = Settings(cassette_mode="off")
    accumulator = RunAccumulator()
    retriever = FixtureRetriever("ctrl-gold-deductible")

    first_turn_tc = ReplayToolCall(
        id="call_test_001",
        function=ReplayFunction(name="coverage_calculator", arguments=_ARGS_JSON),
    )
    captured_second_turn_messages: list[dict[str, Any]] = []
    call_count: list[int] = [0]

    def _complete(**kwargs: Any) -> CompletionResult:
        call_count[0] += 1
        if call_count[0] == 1:
            return CompletionResult(content="", tool_calls=[first_turn_tc])
        captured_second_turn_messages.extend(kwargs["messages"])
        return CompletionResult(content="Your estimated cost is $100.", tool_calls=[])

    mock_provider = MagicMock()
    mock_provider.accumulator = accumulator
    mock_provider.complete.side_effect = _complete

    agent = CoverageAgent(settings=settings, retriever=retriever, provider=mock_provider)
    response = agent.answer("What does my Gold plan cover for a lab?", member_id="MBR-002")

    assert not response.refused
    tool_messages = [m for m in captured_second_turn_messages if m.get("role") == "tool"]
    assert tool_messages, "expected at least one tool message on the second turn"

    expected_content = json.dumps(run_coverage_calculator(json.loads(_ARGS_JSON)))
    for msg in tool_messages:
        assert msg["tool_call_id"] == first_turn_tc.id
        assert msg["content"] == expected_content
