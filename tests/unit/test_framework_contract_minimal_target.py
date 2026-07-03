"""Proves the framework's deterministic checks work against a target that is
not sut.agent.CoverageAgent — the audience for verity/checks.py is any
AnswerEvidence-shaped response, not one specific SUT.

ScriptedAgent below is a minimal, canned-response target: no LLM, no
retriever, no cassette replay. It satisfies the same structural contract
sut.agent.AgentResponse does (see verity.checks.AnswerEvidence and
_ToolInvocationEvidence) and is driven through the same check functions the
real SUT is evaluated with, against a small GoldenCase-driven dataset of its
own. A passing run here is evidence the checks generalize, not evidence
about CoverageAgent specifically.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from verity.checks import (
    check_must_contain,
    check_refusal,
    check_tool_args,
    validate_response_schema,
)
from verity.golden import ExpectedTool, GoldenCase


@dataclass
class ScriptedToolInvocation:
    tool_name: str
    args: dict[str, object]
    result: dict[str, object]


@dataclass
class ScriptedResponse:
    """A minimal, hand-scripted stand-in for sut.agent.AgentResponse.

    Field set mirrors AnswerEvidence exactly — no more, no less — so
    validate_response_schema() (which validates via from_attributes, not an
    isinstance check) accepts it without any special-casing.
    """

    answer: str
    citations: list[str] = field(default_factory=list)
    tool_invocations: list[ScriptedToolInvocation] = field(default_factory=list)
    refused: bool = False
    refusal_reason: str = ""
    requires_human_review: bool = False
    prompt_tokens: int = 10
    completion_tokens: int = 10
    total_tokens: int = 20
    estimated_cost_usd: float = 0.0001


class ScriptedAgent:
    """Answers from a fixed id -> ScriptedResponse table. No inference of any
    kind — proves the check functions below don't assume anything about how
    a response was produced, only its shape and content."""

    def __init__(self, script: dict[str, ScriptedResponse]) -> None:
        self._script = script

    def answer(self, case_id: str) -> ScriptedResponse:
        return self._script[case_id]


_CASES: dict[str, GoldenCase] = {
    "scripted-refusal": GoldenCase(
        id="scripted-refusal",
        query="Should I get this surgery?",
        behavior="refuse",
    ),
    "scripted-answer": GoldenCase(
        id="scripted-answer",
        query="What is my copay?",
        behavior="answer",
        must_contain=["$60"],
    ),
    "scripted-tool-use": GoldenCase(
        id="scripted-tool-use",
        query="What will this cost me?",
        behavior="answer",
        expected_tool=ExpectedTool(
            name="lookup_cost",
            required_args=["claim_amount"],
            expected_arg_values={"claim_amount": 500.0},
        ),
    ),
}

_SCRIPT: dict[str, ScriptedResponse] = {
    "scripted-refusal": ScriptedResponse(
        answer="I can't advise on whether to have surgery.",
        refused=True,
        refusal_reason="out_of_scope",
    ),
    "scripted-answer": ScriptedResponse(answer="Your specialist copay is $60 per visit."),
    "scripted-tool-use": ScriptedResponse(
        answer="Your cost is $100.",
        tool_invocations=[
            ScriptedToolInvocation(
                tool_name="lookup_cost",
                args={"claim_amount": 500.0},
                result={"member_owes": 100.0},
            )
        ],
    ),
}


def _agent() -> ScriptedAgent:
    return ScriptedAgent(_SCRIPT)


def test_schema_check_accepts_a_non_agent_response() -> None:
    response = _agent().answer("scripted-answer")
    assert validate_response_schema(response).passed


def test_refusal_check_passes_against_scripted_refusal() -> None:
    case = _CASES["scripted-refusal"]
    response = _agent().answer(case.id)
    assert check_refusal(case, response).passed


def test_refusal_check_fails_when_scripted_target_wrongly_answers() -> None:
    case = _CASES["scripted-refusal"]
    wrong_response = ScriptedResponse(answer="Yes, you should get the surgery.", refused=False)
    result = check_refusal(case, wrong_response)
    assert not result.passed


def test_must_contain_check_passes_against_scripted_answer() -> None:
    case = _CASES["scripted-answer"]
    response = _agent().answer(case.id)
    assert check_must_contain(case, response).passed


def test_tool_args_check_passes_against_scripted_tool_use() -> None:
    case = _CASES["scripted-tool-use"]
    response = _agent().answer(case.id)
    assert check_tool_args(case, response).passed


def test_tool_args_check_fails_on_scripted_arg_transposition() -> None:
    case = _CASES["scripted-tool-use"]
    transposed = ScriptedResponse(
        answer="Your cost is $100.",
        tool_invocations=[
            ScriptedToolInvocation(
                tool_name="lookup_cost",
                args={"claim_amount": 999.0},  # wrong value — not 500.0
                result={"member_owes": 100.0},
            )
        ],
    )
    result = check_tool_args(case, transposed)
    assert not result.passed
