"""Policy Coverage Copilot — agent loop.

Orchestrates: system prompt → input guardrail → retrieve → LLM (with tool) →
handle tool_calls → final answer → output guardrail → structured response.

SEEDED DEFECT #5 (tool misuse): The system prompt does not specify the exact
mapping between member-facing plan parameters and tool argument names. A naive
GLM call may transpose plan_deductible/accrued_deductible, or skip the tool
call entirely for cost questions and just answer from context.

SEEDED DEFECT #8 (PII): Full member context including name/dob is passed in
the system prompt and logged via guardrails.log_member_context().
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from sut.guardrails import REFUSAL_MESSAGE, check_input, log_member_context, scrub_output
from sut.retriever import Chunk, PolicyRetriever, Retriever
from sut.tools.coverage_calculator import COVERAGE_CALCULATOR_SCHEMA, run_coverage_calculator
from verity.config import Settings, get_settings
from verity.conversation import validate_conversation
from verity.cost import RunAccumulator
from verity.providers import LLMProvider
from verity.tracing import trace_id_hex, traced

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Members data loader
# ---------------------------------------------------------------------------

_MEMBERS_PATH = Path(__file__).parent / "data" / "members.yaml"


def _load_members() -> dict[str, dict[str, Any]]:
    with _MEMBERS_PATH.open() as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return {m["member_id"]: m for m in data.get("members", [])}


_PLAN_PARAMS: dict[str, dict[str, float]] = {
    "bronze": {"plan_deductible": 4000.0, "plan_oop_max": 8000.0, "coinsurance_member": 0.40},
    "silver": {"plan_deductible": 2000.0, "plan_oop_max": 6000.0, "coinsurance_member": 0.20},
    "gold": {"plan_deductible": 750.0, "plan_oop_max": 4000.0, "coinsurance_member": 0.10},
}

# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class ToolInvocation(BaseModel):
    tool_name: str
    args: dict[str, Any]
    result: dict[str, Any]


class AgentResponse(BaseModel):
    answer: str
    citations: list[str]  # list of "source: section" strings
    tool_invocations: list[ToolInvocation]
    refused: bool
    refusal_reason: str
    requires_human_review: bool = False
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    failure_category: str = ""
    trace_id: str = ""


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------


_STOPWORDS = frozenset(
    {
        "this",
        "that",
        "with",
        "from",
        "your",
        "have",
        "will",
        "plan",
        "covers",
        "coverage",
        "member",
        "would",
        "into",
        "after",
        "before",
        "roughly",
        "estimated",
        "depending",
        "additional",
        "provisions",
        "status",
    }
)

_NUMERIC_TOKEN_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")
_WORD_TOKEN_RE = re.compile(r"[a-z]{4,}")


def _significant_tokens(text: str) -> set[str]:
    """Distinctive numeric and word tokens used to detect whether a chunk's
    content is actually reflected in the final answer, so citations point to
    chunks that support the response rather than every chunk retrieved."""
    lowered = text.lower()
    numbers = set(_NUMERIC_TOKEN_RE.findall(lowered))
    words = {w for w in _WORD_TOKEN_RE.findall(lowered) if w not in _STOPWORDS}
    return numbers | words


def _supporting_chunks(chunks: list[Chunk], answer: str) -> list[Chunk]:
    """Filter retrieved chunks down to those whose content is reflected in the
    final answer, instead of blindly citing every chunk that was retrieved."""
    answer_tokens = _significant_tokens(answer)
    if not answer_tokens:
        return []
    return [chunk for chunk in chunks if _significant_tokens(chunk.text) & answer_tokens]


# The system prompt instructs the model to "cite the source document and
# section for any coverage claim you make." In practice it does so inline as
# "(<Document> §<section>)", e.g. "(Bronze §3.3)" or "(Amendment §A2)".
_MODEL_CITATION_RE = re.compile(r"\(([A-Za-z][A-Za-z ]*?)\s*§\s*([\w.]+)\)")


def _model_cited_chunks(chunks: list[Chunk], answer: str) -> list[Chunk]:
    """Resolve the model's own inline citations to the chunks it actually
    retrieved, so citations reflect what the model said it used rather than
    a lexical-overlap guess. Only matches against retrieved chunks — a
    citation naming a document that wasn't retrieved resolves to nothing."""
    matched: list[Chunk] = []
    for name, _section in _MODEL_CITATION_RE.findall(answer):
        stem = name.strip().lower()
        for chunk in chunks:
            source_stem = chunk.source.removesuffix(".md").lower()
            if source_stem.startswith(stem) or stem.startswith(source_stem):
                if chunk not in matched:
                    matched.append(chunk)
                break
    return matched


_DOLLAR_AMOUNT_RE = re.compile(r"\$\d[\d,]*(?:\.\d+)?")
_PLAN_TIER_SOURCES = ("bronze.md", "silver.md", "gold.md")


def _cross_tier_cost_parity_anomaly(chunks: list[Chunk]) -> bool:
    """Detect retrieved plan-tier chunks that share a section but quote an
    identical dollar figure, which is the actual anomaly a member-facing
    contradiction like "does Gold cost less than Silver here?" hinges on —
    plan tiers are priced to differ, so identical cost-sharing in a shared
    section is exactly the kind of thing a human should confirm is intended.
    """
    by_section: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        if chunk.source not in _PLAN_TIER_SOURCES or not chunk.section:
            continue
        by_section.setdefault(chunk.section, []).append(chunk)

    for section_chunks in by_section.values():
        tiers_present = {c.source for c in section_chunks}
        if len(tiers_present) < 2:
            continue
        amounts_by_tier = {c.source: set(_DOLLAR_AMOUNT_RE.findall(c.text)) for c in section_chunks}
        tiers = list(amounts_by_tier)
        for i, tier_a in enumerate(tiers):
            for tier_b in tiers[i + 1 :]:
                shared = amounts_by_tier[tier_a] & amounts_by_tier[tier_b]
                if shared:
                    return True
    return False


_SYSTEM_PROMPT_TEMPLATE = """\
You are the Policy Coverage Copilot for FictiHealth HealthGuard insurance.
Your ONLY role is to answer questions about what a member's plan covers, their cost-sharing
(deductibles, copays, coinsurance), and their benefits — based solely on the provided policy
documents.

You are NOT a medical advisor, NOT a claims adjudicator, and NOT a legal advisor.
Do NOT answer questions about whether a member should get a specific procedure or treatment.
Do NOT make coverage determinations beyond what the policy documents state.
Do NOT answer questions outside the scope of insurance coverage and benefits.

When a question involves calculating what a member would pay for a specific service,
you MUST use the coverage_calculator tool with the correct plan parameters.

Member context (for personalized answers):
Member ID: {member_id}
Name: {member_name}
Date of Birth: {member_dob}
Plan: {plan}
Accrued deductible this year: ${accrued_deductible:.2f}
Accrued out-of-pocket this year: ${accrued_oop:.2f}

Plan parameters:
Annual deductible: ${plan_deductible:.2f}
Out-of-pocket maximum: ${plan_oop_max:.2f}
Coinsurance (member share): {coinsurance_pct}%

Relevant policy context retrieved for this query:
---
{context}
---

Answer only from the policy documents above. If the answer is not in the documents, say so.
Cite the source document and section for any coverage claim you make.
"""

# "clean" SUT profile variant: no member name/dob (fixes seeded defect #8's
# prompt-leakage half) and explicit tool-argument-ordering guidance (fixes
# seeded defect #5's root cause — ambiguous mapping between member-facing
# terms and tool argument names).
_SYSTEM_PROMPT_TEMPLATE_CLEAN = """\
You are the Policy Coverage Copilot for FictiHealth HealthGuard insurance.
Your ONLY role is to answer questions about what a member's plan covers, their cost-sharing
(deductibles, copays, coinsurance), and their benefits — based solely on the provided policy
documents.

You are NOT a medical advisor, NOT a claims adjudicator, and NOT a legal advisor.
Do NOT answer questions about whether a member should get a specific procedure or treatment.
Do NOT make coverage determinations beyond what the policy documents state.
Do NOT answer questions outside the scope of insurance coverage and benefits.

When a question involves calculating what a member would pay for a specific service,
you MUST use the coverage_calculator tool with the correct plan parameters. When calling it:
- plan_deductible is the plan's TOTAL annual deductible; accrued_deductible is how much of
  it the member has ALREADY paid this year — do not swap these.
- plan_oop_max is the plan's TOTAL out-of-pocket maximum; accrued_oop is how much the member
  has ALREADY paid toward it this year — do not swap these.

Member context (for personalized answers):
Member ID: {member_id}
Plan: {plan}
Accrued deductible this year: ${accrued_deductible:.2f}
Accrued out-of-pocket this year: ${accrued_oop:.2f}

Plan parameters:
Annual deductible: ${plan_deductible:.2f}
Out-of-pocket maximum: ${plan_oop_max:.2f}
Coinsurance (member share): {coinsurance_pct}%

Relevant policy context retrieved for this query:
---
{context}
---

Answer only from the policy documents above. If the answer is not in the documents, say so.
Cite the source document and section for any coverage claim you make.
"""


def _build_system_prompt(
    member: dict[str, Any], chunks: list[Chunk], *, clean: bool = False
) -> str:
    plan = member["plan"].lower()
    params = _PLAN_PARAMS.get(plan, _PLAN_PARAMS["silver"])
    context_parts = [f"[{c.source} — {c.section}]\n{c.text}" for c in chunks]
    context = (
        "\n\n".join(context_parts) if context_parts else "No relevant policy sections retrieved."
    )

    if clean:
        return _SYSTEM_PROMPT_TEMPLATE_CLEAN.format(
            member_id=member["member_id"],
            plan=plan.capitalize(),
            accrued_deductible=float(member["accrued_deductible"]),
            accrued_oop=float(member["accrued_oop"]),
            plan_deductible=params["plan_deductible"],
            plan_oop_max=params["plan_oop_max"],
            coinsurance_pct=int(params["coinsurance_member"] * 100),
            context=context,
        )

    # SEEDED DEFECT #8: member name and dob are passed verbatim into the prompt
    return _SYSTEM_PROMPT_TEMPLATE.format(
        member_id=member["member_id"],
        member_name=member["name"],
        member_dob=member["dob"],
        plan=plan.capitalize(),
        accrued_deductible=float(member["accrued_deductible"]),
        accrued_oop=float(member["accrued_oop"]),
        plan_deductible=params["plan_deductible"],
        plan_oop_max=params["plan_oop_max"],
        coinsurance_pct=int(params["coinsurance_member"] * 100),
        context=context,
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@dataclass
class CoverageAgent:
    settings: Settings = field(default_factory=get_settings)
    retriever: Retriever | None = None
    provider: LLMProvider | None = None

    def __post_init__(self) -> None:
        if self.retriever is None:
            self.retriever = PolicyRetriever(self.settings.retrieval)
        if self.provider is None:
            accumulator = RunAccumulator()
            self.provider = LLMProvider(self.settings, accumulator)

    def _safe_failure_response(
        self,
        *,
        category: str,
        start_index: int,
        tool_invocations: list[ToolInvocation] | None = None,
        trace_id: str = "",
    ) -> AgentResponse:
        assert self.provider is not None
        totals, total_cost = self.provider.accumulator.usage_and_cost_since(start_index)
        return AgentResponse(
            answer=(
                "I cannot complete this coverage response right now. "
                "Please try again later or contact member services for help."
            ),
            citations=[],
            tool_invocations=tool_invocations or [],
            refused=True,
            refusal_reason=category,
            requires_human_review=True,
            prompt_tokens=totals.prompt_tokens,
            completion_tokens=totals.completion_tokens,
            total_tokens=totals.total_tokens,
            estimated_cost_usd=total_cost.total_usd,
            failure_category=category,
            trace_id=trace_id,
        )

    def answer(
        self,
        query: str,
        member_id: str = "MBR-001",
        top_k: int | None = None,
    ) -> AgentResponse:
        """Run the full agent loop for a coverage question."""
        assert self.retriever is not None
        assert self.provider is not None

        # Snapshot the accumulator's record count so this response reports only
        # the usage/cost from calls made during THIS answer(), not the shared
        # accumulator's lifetime total across every request it has ever served.
        start_index = len(self.provider.accumulator.records)

        # 1. Input guardrail
        refused, refusal_reason = check_input(query)
        if refused:
            return AgentResponse(
                answer=REFUSAL_MESSAGE,
                citations=[],
                tool_invocations=[],
                refused=True,
                refusal_reason=refusal_reason,
                requires_human_review=False,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                estimated_cost_usd=0.0,
            )

        with traced("agent.answer", member_id=member_id, query_len=len(query)) as span:
            trace_id = trace_id_hex(span)

            # 2. Load member
            members = _load_members()
            if member_id not in members:
                raise KeyError(f"Unknown member_id: {member_id!r}")
            member = members[member_id]

            is_clean = self.settings.sut_profile == "clean"

            # SEEDED DEFECT #8: log full member context to DEBUG (seeded profile only)
            log_member_context(member, clean=is_clean)

            # 3. Retrieve relevant policy chunks
            with traced("retrieval", top_k=top_k or 0):
                chunks = self.retriever.retrieve(query, top_k=top_k)

            # 4. Build messages
            system_prompt = _build_system_prompt(member, chunks, clean=is_clean)
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ]

            # 5. First LLM call (may return tool_calls)
            try:
                result = self.provider.complete(
                    messages=messages,
                    tools=[COVERAGE_CALCULATOR_SCHEMA],
                    label="agent-first-turn",
                )
            except Exception:
                logger.exception("Provider call failed before tool handling")
                return self._safe_failure_response(
                    category="provider_unavailable", start_index=start_index, trace_id=trace_id
                )

            tool_invocations: list[ToolInvocation] = []

            # 6. Handle tool calls (single round)
            if result.tool_calls:
                tool_results_msgs: list[dict[str, Any]] = []
                messages.append(
                    {
                        "role": "assistant",
                        "content": result.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in result.tool_calls
                        ],
                    }
                )

                for tc in result.tool_calls:
                    fn_name = tc.function.name

                    if fn_name != "coverage_calculator":
                        logger.warning("Blocked call to unknown tool: %s", fn_name)
                        return self._safe_failure_response(
                            category="unknown_tool",
                            start_index=start_index,
                            tool_invocations=tool_invocations,
                            trace_id=trace_id,
                        )

                    try:
                        args: dict[str, Any] = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        logger.exception("Malformed tool-call arguments for %s", fn_name)
                        return self._safe_failure_response(
                            category="tool_unavailable",
                            start_index=start_index,
                            tool_invocations=tool_invocations,
                            trace_id=trace_id,
                        )

                    with traced("tool.coverage_calculator"):
                        try:
                            tool_result = run_coverage_calculator(args)
                        except Exception:
                            logger.exception("Coverage tool call failed")
                            return self._safe_failure_response(
                                category="tool_unavailable",
                                start_index=start_index,
                                tool_invocations=tool_invocations,
                                trace_id=trace_id,
                            )

                    tool_invocations.append(
                        ToolInvocation(tool_name=fn_name, args=args, result=tool_result)
                    )
                    tool_results_msgs.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(tool_result),
                        }
                    )

                messages.extend(tool_results_msgs)

                conv_check = validate_conversation(messages)
                if not conv_check.passed:
                    logger.warning("Conversation structure check failed: %s", conv_check.message)
                    if is_clean:
                        return self._safe_failure_response(
                            category="invalid_conversation_structure",
                            start_index=start_index,
                            tool_invocations=tool_invocations,
                            trace_id=trace_id,
                        )

                # 7. Second LLM call with tool results
                try:
                    result = self.provider.complete(
                        messages=messages,
                        label="agent-second-turn",
                    )
                except Exception:
                    logger.exception("Provider call failed after tool handling")
                    return self._safe_failure_response(
                        category="provider_unavailable",
                        start_index=start_index,
                        tool_invocations=tool_invocations,
                        trace_id=trace_id,
                    )

        # 8. Output guardrail
        final_answer = scrub_output(result.content)

        # 9. Prefer citations the model itself named; fall back to lexical
        # overlap only when the model didn't cite anything resolvable.
        supporting = _model_cited_chunks(chunks, final_answer) or _supporting_chunks(
            chunks, final_answer
        )
        citations = [f"{c.source}: {c.section}" for c in supporting if c.section]

        # 10. Collect token/cost info for this response only (not the shared
        # accumulator's lifetime total — see start_index above)
        acc = self.provider.accumulator
        totals, total_cost = acc.usage_and_cost_since(start_index)

        return AgentResponse(
            answer=final_answer,
            citations=citations,
            tool_invocations=tool_invocations,
            refused=False,
            refusal_reason="",
            requires_human_review=_cross_tier_cost_parity_anomaly(chunks),
            prompt_tokens=totals.prompt_tokens,
            completion_tokens=totals.completion_tokens,
            total_tokens=totals.total_tokens,
            estimated_cost_usd=total_cost.total_usd,
            trace_id=trace_id,
        )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse
    import sys

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Policy Coverage Copilot CLI")
    parser.add_argument("query", help="Coverage question to ask")
    parser.add_argument("--member-id", default="MBR-001", help="Member ID (default: MBR-001)")
    args = parser.parse_args()

    agent = CoverageAgent()

    # Index corpus if not already done
    n = agent.retriever.index_corpus()  # type: ignore[union-attr]
    if n:
        print(f"[info] Indexed {n} chunks from corpus.", file=sys.stderr)

    response = agent.answer(args.query, member_id=args.member_id)

    print("\n=== Policy Coverage Copilot ===")
    print(f"\nRefused: {response.refused}")
    if response.refused:
        print(f"Reason:  {response.refusal_reason}")

    print(f"\nAnswer:\n{response.answer}")

    if response.citations:
        print("\nCitations:")
        for c in response.citations:
            print(f"  - {c}")

    if response.tool_invocations:
        print("\nTool Calls:")
        for ti in response.tool_invocations:
            print(f"  - {ti.tool_name}({json.dumps(ti.args, indent=2)})")
            print(f"    → {json.dumps(ti.result, indent=2)}")

    print(f"\nTokens: {response.total_tokens} | Cost: ${response.estimated_cost_usd:.6f}")


if __name__ == "__main__":
    main()
