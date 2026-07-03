"""Tool-call argument validation against a golden case's expected_tool."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from verity.check_result import CheckResult
from verity.golden import GoldenCase

ToolArgValidator = Callable[[dict[str, Any]], None]
_TOOL_ARG_VALIDATORS: dict[str, tuple[ToolArgValidator, str]] = {}


def register_tool_arg_validator(
    name: str, fn: ToolArgValidator, *, label: str | None = None
) -> None:
    """Register target-owned validation for a named tool's argument schema."""
    _TOOL_ARG_VALIDATORS[name] = (fn, label or name)


def _check_single_invocation(expected: Any, args: dict[str, Any]) -> str | None:
    """Return an error message for one invocation's args, or None if it's valid."""
    missing_args = [a for a in expected.required_args if a not in args]
    if missing_args:
        return f"missing required args: {missing_args}"

    registered = _TOOL_ARG_VALIDATORS.get(expected.name)
    if registered is not None:
        validator, label = registered
        try:
            validator(args)
        except Exception as exc:
            return f"failed {label} validation: {exc}"

    mismatches: list[str] = []
    for arg_name, expected_val in expected.expected_arg_values.items():
        actual_val = args.get(arg_name)
        if actual_val != expected_val:
            mismatches.append(f"{arg_name}: expected {expected_val!r}, got {actual_val!r}")
    if mismatches:
        return "arg value mismatch: " + "; ".join(mismatches)

    return None


def check_tool_args(case: GoldenCase, response: Any) -> CheckResult:
    """Verify the full tool-call trace matches the case's expectation, not just one call.

    Detects:
    - Tool skipped entirely (tool_invocations empty when expected_tool is set)
    - Any call to a tool other than the expected one (unauthorized/hallucinated tool use)
    - Redundant duplicate calls to the expected tool (a model that calls the tool twice,
      once wrong and once right, must not pass just because one call looked correct)
    - Arguments that fail registered tool-specific validation (wrong types / constraints)
    - Arguments that differ from expected_arg_values (transposition detection)
    """
    expected = case.expected_tool
    if expected is None:
        return CheckResult(True, "No tool expected — skipped")

    invocations: list[Any] = list(getattr(response, "tool_invocations", []))
    matching = [ti for ti in invocations if getattr(ti, "tool_name", "") == expected.name]
    unexpected = [ti for ti in invocations if getattr(ti, "tool_name", "") != expected.name]

    if not matching:
        called_names = [getattr(ti, "tool_name", "?") for ti in invocations]
        return CheckResult(
            False,
            f"Expected tool '{expected.name}' not called. Called: {called_names or ['none']}",
        )

    if unexpected:
        unexpected_names = [getattr(ti, "tool_name", "?") for ti in unexpected]
        return CheckResult(
            False, f"Unexpected tool call(s) beyond '{expected.name}': {unexpected_names}"
        )

    if len(matching) > 1:
        return CheckResult(
            False,
            f"Tool '{expected.name}' called {len(matching)} times; expected exactly once",
        )

    args: dict[str, Any] = dict(getattr(matching[0], "args", {}))
    error = _check_single_invocation(expected, args)
    if error is not None:
        return CheckResult(False, f"Tool call {error}")

    return CheckResult(True)
