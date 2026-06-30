"""Deterministic coverage cost calculator.

This is a pure function — no LLM calls, no side effects. It computes exactly
what a member will pay for a covered claim given their plan parameters and
current accumulator state. Unit-tested to exhaustion in tests/unit/.

SEEDED DEFECT #5 LOCATION — in the agent's invocation, not here:
The tool schema intentionally uses ambiguous parameter names so a naive agent
may transpose 'accrued_deductible' and 'plan_deductible', or forget to pass
'accrued_oop', producing wrong cost breakdowns. The function itself is correct.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Input / output models (Pydantic v2)
# ---------------------------------------------------------------------------

class CoverageInput(BaseModel):
    """Input parameters for the coverage calculator.

    All dollar amounts are in USD. Coinsurance is expressed as the MEMBER's
    share as a decimal (e.g. 0.20 for 20% member / 80% plan).
    """

    claim_amount: float = Field(gt=0, description="Allowed amount for the service in USD")
    plan_deductible: float = Field(ge=0, description="Member's annual plan deductible")
    accrued_deductible: float = Field(ge=0, description="Deductible already paid this year")
    plan_oop_max: float = Field(ge=0, description="Member's annual out-of-pocket maximum")
    accrued_oop: float = Field(ge=0, description="Out-of-pocket already accrued this year")
    coinsurance_member: float = Field(
        ge=0, le=1, description="Member coinsurance as a decimal (e.g. 0.20 for 20%)"
    )
    copay: float = Field(
        default=0.0, ge=0, description="Fixed copay in USD; use 0 if coinsurance applies"
    )

    @field_validator("accrued_deductible")
    @classmethod
    def _accrued_deductible_not_exceed_plan(cls, v: float, info: Any) -> float:
        plan_ded = info.data.get("plan_deductible", 0.0)
        if v > plan_ded:
            raise ValueError("accrued_deductible cannot exceed plan_deductible")
        return v

    @field_validator("accrued_oop")
    @classmethod
    def _accrued_oop_not_exceed_plan(cls, v: float, info: Any) -> float:
        plan_oop = info.data.get("plan_oop_max", 0.0)
        if v > plan_oop:
            raise ValueError("accrued_oop cannot exceed plan_oop_max")
        return v


class CoverageResult(BaseModel):
    """Cost breakdown for a single claim."""

    claim_amount: float
    remaining_deductible_before: float
    applied_to_deductible: float
    amount_subject_to_coinsurance: float
    member_coinsurance: float
    member_copay: float
    member_total: float
    plan_pays: float
    remaining_oop_before: float
    oop_cap_applied: bool
    member_total_after_oop_cap: float
    plan_pays_after_oop_cap: float


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

def calculate_coverage(inp: CoverageInput) -> CoverageResult:
    """Compute the member's cost and plan's cost for a single covered claim."""
    remaining_ded = inp.plan_deductible - inp.accrued_deductible
    remaining_oop = inp.plan_oop_max - inp.accrued_oop

    # 1. Apply remaining deductible
    applied_to_ded = min(inp.claim_amount, remaining_ded)
    after_deductible = inp.claim_amount - applied_to_ded

    # 2. Apply copay (if applicable) or coinsurance to post-deductible amount
    if inp.copay > 0:
        member_coinsurance = 0.0
        member_copay = min(inp.copay, after_deductible)
        plan_pays_coinsurance = after_deductible - member_copay
    else:
        member_copay = 0.0
        member_coinsurance = after_deductible * inp.coinsurance_member
        plan_pays_coinsurance = after_deductible * (1 - inp.coinsurance_member)

    # 3. Sum member obligation pre-OOP-cap
    member_total = applied_to_ded + member_coinsurance + member_copay
    plan_total = plan_pays_coinsurance

    # 4. Apply OOP max cap
    oop_cap_applied = member_total > remaining_oop
    if oop_cap_applied:
        member_total_after_cap = remaining_oop
        plan_pays_after_cap = inp.claim_amount - remaining_oop
    else:
        member_total_after_cap = member_total
        plan_pays_after_cap = plan_total  # deductible goes to member, already subtracted
        # Recalculate: plan pays = claim - member total
        plan_pays_after_cap = inp.claim_amount - member_total

    return CoverageResult(
        claim_amount=inp.claim_amount,
        remaining_deductible_before=remaining_ded,
        applied_to_deductible=applied_to_ded,
        amount_subject_to_coinsurance=after_deductible,
        member_coinsurance=member_coinsurance,
        member_copay=member_copay,
        member_total=member_total,
        plan_pays=plan_total,
        remaining_oop_before=remaining_oop,
        oop_cap_applied=oop_cap_applied,
        member_total_after_oop_cap=member_total_after_cap,
        plan_pays_after_oop_cap=plan_pays_after_cap,
    )


# ---------------------------------------------------------------------------
# OpenAI function-calling tool schema (used by the agent)
# SEEDED DEFECT #5: The ambiguous naming of 'accrued_deductible' vs
# 'plan_deductible' and no explicit ordering guidance makes it easy for a
# naive agent to transpose these values when constructing the tool call.
# ---------------------------------------------------------------------------

COVERAGE_CALCULATOR_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "coverage_calculator",
        "description": (
            "Calculate the member's out-of-pocket cost and the plan's payment for a covered "
            "health-care service. Requires the claim amount, plan parameters, and the member's "
            "current deductible and OOP accumulator values."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "claim_amount": {
                    "type": "number",
                    "description": "The allowed amount for the service in USD.",
                },
                "plan_deductible": {
                    "type": "number",
                    "description": "The plan's annual deductible (total, not remaining) in USD.",
                },
                "accrued_deductible": {
                    "type": "number",
                    "description": "How much deductible the member has already paid this year.",
                },
                "plan_oop_max": {
                    "type": "number",
                    "description": "The plan's annual out-of-pocket maximum in USD.",
                },
                "accrued_oop": {
                    "type": "number",
                    "description": "How much out-of-pocket the member has already paid this year.",
                },
                "coinsurance_member": {
                    "type": "number",
                    "description": "Member coinsurance as a decimal (e.g. 0.20 for 20%).",
                },
                "copay": {
                    "type": "number",
                    "description": "Fixed copay in USD. Use 0 if coinsurance applies instead.",
                },
            },
            "required": [
                "claim_amount",
                "plan_deductible",
                "accrued_deductible",
                "plan_oop_max",
                "accrued_oop",
                "coinsurance_member",
            ],
        },
    },
}


def run_coverage_calculator(args: dict[str, Any]) -> dict[str, Any]:
    """Parse tool-call arguments and run the calculator. Returns a JSON-serialisable dict."""
    inp = CoverageInput(**args)
    result = calculate_coverage(inp)
    return result.model_dump()
