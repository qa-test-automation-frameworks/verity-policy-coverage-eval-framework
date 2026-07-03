"""Structural and invariant validation for AgentResponse-shaped objects."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from verity.check_result import CheckResult


class _ToolInvocationEvidence(BaseModel):
    """Structural mirror of sut.agent.ToolInvocation.

    Duplicated here (rather than imported) because verity must not import sut
    (see verity.checks module docstring) — this module is framework code that
    also validates the demo SUT's output, and sut already imports from verity.
    """

    model_config = ConfigDict(from_attributes=True)

    tool_name: str
    args: dict[str, Any]
    result: dict[str, Any]


class AnswerEvidence(BaseModel):
    """Structural + invariant validation for one AgentResponse.

    Mirrors sut.agent.AgentResponse's field shape (see _ToolInvocationEvidence
    docstring for why it's duplicated rather than imported) and additionally
    enforces cross-field invariants a bare type/presence check can't catch:
    a refused response must carry a reason, token counts must be non-negative
    and internally consistent, and cost must be non-negative.
    """

    model_config = ConfigDict(from_attributes=True)

    answer: str
    citations: list[str]
    tool_invocations: list[_ToolInvocationEvidence]
    refused: bool
    refusal_reason: str
    requires_human_review: bool
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float

    @model_validator(mode="after")
    def _refused_responses_must_carry_a_reason(self) -> AnswerEvidence:
        if self.refused and not self.refusal_reason.strip():
            raise ValueError("refused=True but refusal_reason is empty")
        return self

    @model_validator(mode="after")
    def _token_counts_are_non_negative_and_consistent(self) -> AnswerEvidence:
        if self.prompt_tokens < 0 or self.completion_tokens < 0 or self.total_tokens < 0:
            raise ValueError("token counts must be non-negative")
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError(
                f"total_tokens ({self.total_tokens}) != prompt_tokens "
                f"({self.prompt_tokens}) + completion_tokens ({self.completion_tokens})"
            )
        return self

    @model_validator(mode="after")
    def _cost_is_non_negative(self) -> AnswerEvidence:
        if self.estimated_cost_usd < 0:
            raise ValueError("estimated_cost_usd must be non-negative")
        return self


def validate_response_schema(response: Any) -> CheckResult:
    """Verify the response matches the AnswerEvidence contract: required fields,
    correct types, and cross-field invariants (refusal/token/cost consistency)."""
    try:
        AnswerEvidence.model_validate(response, from_attributes=True)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        field_path = ".".join(str(p) for p in first_error["loc"]) or "<model>"
        return CheckResult(False, f"Response schema invalid at {field_path}: {first_error['msg']}")
    return CheckResult(True)
