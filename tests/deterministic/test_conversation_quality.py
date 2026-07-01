"""Tier-1: conversation structure quality gates.

Every message list the real agent sends to the provider — for every golden
case, including multi-turn tool-calling cases — must be structurally sound:
system/user opening turns, matched tool_call ids, no orphaned tool results.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.deterministic.conftest import run_case_capturing_conversations
from verity.config import Settings
from verity.conversation import validate_conversation
from verity.golden import GoldenCase, load_golden

pytestmark = pytest.mark.deterministic

_CASES = load_golden(Path("datasets/golden"))


@pytest.mark.parametrize("case", _CASES, ids=[c.id for c in _CASES])
def test_every_llm_call_conversation_is_well_formed(
    case: GoldenCase, _settings: Settings
) -> None:
    response, conversations = run_case_capturing_conversations(case, _settings)
    if not conversations:
        # The input guardrail can refuse before any LLM call is made at all
        # (see sut.guardrails.check_input) — that's a valid zero-call outcome,
        # not a broken conversation.
        assert response.refused, f"{case.id}: no LLM calls were captured but response wasn't refused"
        return
    for i, messages in enumerate(conversations):
        result = validate_conversation(messages)
        assert result.passed, f"{case.id} (call #{i + 1}): {result.message}"


def test_tool_use_cases_send_multiple_turns(_settings: Settings) -> None:
    """Sanity check that the capture harness actually exercises the tool-call
    path, not just single-turn conversations, for at least one golden case."""
    tool_cases = [c for c in _CASES if c.expected_tool is not None]
    assert tool_cases, "no golden cases with expected_tool — capture harness is undertested"

    found_multi_turn = False
    for case in tool_cases:
        _response, conversations = run_case_capturing_conversations(case, _settings)
        if len(conversations) > 1:
            found_multi_turn = True
            break
    assert found_multi_turn, "expected at least one tool-use case to make >1 LLM call"
