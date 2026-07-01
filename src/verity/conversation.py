"""Structural quality checks for the message list sent to the LLM provider.

Independent of what the *content* of a response says (that's checks.py's
job), a conversation can be structurally broken in ways that would confuse
or silently degrade a provider: a tool message with no matching tool_call_id,
an assistant tool_calls turn never followed by tool results, duplicate
tool_call ids, or a message list that doesn't open with system/user turns.
These checks catch that class of bug at construction time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConversationCheckResult:
    passed: bool
    message: str = ""


def validate_conversation(messages: list[dict[str, Any]]) -> ConversationCheckResult:
    """Validate structural invariants of a chat-completion message list.

    Checks:
    - Non-empty, starts with a system message followed by a user message.
    - Every assistant message with tool_calls has at least one tool_call.
    - Every tool_call id referenced by an assistant message is answered by
      exactly one subsequent tool message with a matching tool_call_id.
    - No tool message references a tool_call id that was never requested.
    - No duplicate tool_call ids within a single assistant turn.
    """
    if not messages:
        return ConversationCheckResult(False, "conversation has no messages")

    if messages[0].get("role") != "system":
        return ConversationCheckResult(False, "first message must have role 'system'")

    if len(messages) < 2 or messages[1].get("role") != "user":
        return ConversationCheckResult(False, "second message must have role 'user'")

    requested_ids: set[str] = set()
    answered_ids: set[str] = set()

    for msg in messages:
        role = msg.get("role")

        if role == "assistant" and msg.get("tool_calls"):
            tool_calls = msg["tool_calls"]
            if not tool_calls:
                return ConversationCheckResult(
                    False, "assistant message has empty tool_calls list"
                )
            turn_ids = [tc["id"] for tc in tool_calls]
            if len(turn_ids) != len(set(turn_ids)):
                return ConversationCheckResult(
                    False, f"duplicate tool_call ids within one assistant turn: {turn_ids}"
                )
            requested_ids.update(turn_ids)

        if role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if not tool_call_id:
                return ConversationCheckResult(False, "tool message missing tool_call_id")
            if tool_call_id not in requested_ids:
                return ConversationCheckResult(
                    False,
                    f"tool message references tool_call_id {tool_call_id!r} "
                    "that was never requested by an assistant turn",
                )
            if tool_call_id in answered_ids:
                return ConversationCheckResult(
                    False, f"tool_call_id {tool_call_id!r} answered more than once"
                )
            answered_ids.add(tool_call_id)

    unanswered = requested_ids - answered_ids
    if unanswered:
        return ConversationCheckResult(
            False, f"tool_call id(s) requested but never answered: {sorted(unanswered)}"
        )

    return ConversationCheckResult(True)
