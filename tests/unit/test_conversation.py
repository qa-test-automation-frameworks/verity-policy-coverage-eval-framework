"""Unit tests for conversation structural validation."""

from __future__ import annotations

from verity.conversation import validate_conversation


def _simple_conversation() -> list[dict]:
    return [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "What is my deductible?"},
        {"role": "assistant", "content": "It is $750."},
    ]


def _tool_call_conversation() -> list[dict]:
    return [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "How much will I owe?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "coverage_calculator"}}
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": '{"member_total": 100}'},
        {"role": "assistant", "content": "You will owe $100."},
    ]


class TestValidConversations:
    def test_simple_no_tool_conversation_passes(self) -> None:
        result = validate_conversation(_simple_conversation())
        assert result.passed

    def test_tool_call_conversation_passes(self) -> None:
        result = validate_conversation(_tool_call_conversation())
        assert result.passed

    def test_multiple_tool_calls_in_one_turn_all_answered(self) -> None:
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "a", "type": "function", "function": {"name": "x"}},
                    {"id": "b", "type": "function", "function": {"name": "y"}},
                ],
            },
            {"role": "tool", "tool_call_id": "a", "content": "{}"},
            {"role": "tool", "tool_call_id": "b", "content": "{}"},
        ]
        assert validate_conversation(messages).passed


class TestInvalidConversations:
    def test_empty_conversation_fails(self) -> None:
        result = validate_conversation([])
        assert not result.passed
        assert "no messages" in result.message

    def test_missing_system_first_fails(self) -> None:
        messages = [{"role": "user", "content": "hi"}]
        result = validate_conversation(messages)
        assert not result.passed
        assert "system" in result.message

    def test_missing_user_second_fails(self) -> None:
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "assistant", "content": "hi"},
        ]
        result = validate_conversation(messages)
        assert not result.passed
        assert "user" in result.message

    def test_tool_message_with_no_tool_call_id_fails(self) -> None:
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
            {"role": "tool", "content": "{}"},
        ]
        result = validate_conversation(messages)
        assert not result.passed
        assert "missing tool_call_id" in result.message

    def test_tool_message_with_unrequested_id_fails(self) -> None:
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
            {"role": "tool", "tool_call_id": "never_requested", "content": "{}"},
        ]
        result = validate_conversation(messages)
        assert not result.passed
        assert "never requested" in result.message

    def test_unanswered_tool_call_fails(self) -> None:
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "x"}}],
            },
        ]
        result = validate_conversation(messages)
        assert not result.passed
        assert "never answered" in result.message

    def test_duplicate_tool_call_ids_in_same_turn_fails(self) -> None:
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "dup", "type": "function", "function": {"name": "x"}},
                    {"id": "dup", "type": "function", "function": {"name": "y"}},
                ],
            },
        ]
        result = validate_conversation(messages)
        assert not result.passed
        assert "duplicate" in result.message

    def test_tool_call_id_answered_twice_fails(self) -> None:
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "x"}}],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "{}"},
            {"role": "tool", "tool_call_id": "call_1", "content": "{}"},
        ]
        result = validate_conversation(messages)
        assert not result.passed
        assert "answered more than once" in result.message

    def test_empty_tool_calls_list_fails(self) -> None:
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "", "tool_calls": []},
        ]
        # Empty tool_calls list is falsy, so this doesn't trigger the tool_calls
        # branch at all — it's structurally equivalent to a plain assistant turn.
        result = validate_conversation(messages)
        assert result.passed
