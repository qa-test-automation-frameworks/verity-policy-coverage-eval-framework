"""Property-based tests for calculate_coverage() — a pure function with no
I/O, so its invariants should hold across the entire valid input space, not
just the hand-picked examples in test_coverage_calculator.py."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sut.tools.coverage_calculator import CoverageInput, calculate_coverage


@st.composite
def coverage_inputs(draw: st.DrawFn) -> CoverageInput:
    """Generates CoverageInput values respecting its own field constraints
    (accrued_deductible <= plan_deductible, accrued_oop <= plan_oop_max)."""
    plan_deductible = draw(st.floats(min_value=0, max_value=10_000, allow_nan=False))
    accrued_deductible = draw(st.floats(min_value=0, max_value=plan_deductible, allow_nan=False))
    plan_oop_max = draw(st.floats(min_value=0, max_value=20_000, allow_nan=False))
    accrued_oop = draw(st.floats(min_value=0, max_value=plan_oop_max, allow_nan=False))
    coinsurance_member = draw(st.floats(min_value=0, max_value=1, allow_nan=False))
    claim_amount = draw(
        st.floats(min_value=0.01, max_value=50_000, allow_nan=False, exclude_min=False)
    )
    copay = draw(st.floats(min_value=0, max_value=1_000, allow_nan=False))
    return CoverageInput(
        claim_amount=claim_amount,
        plan_deductible=plan_deductible,
        accrued_deductible=accrued_deductible,
        plan_oop_max=plan_oop_max,
        accrued_oop=accrued_oop,
        coinsurance_member=coinsurance_member,
        copay=copay,
    )


@given(inp=coverage_inputs())
@settings(max_examples=200)
def test_member_and_plan_shares_sum_to_claim_amount(inp: CoverageInput) -> None:
    result = calculate_coverage(inp)
    total = result.member_total_after_oop_cap + result.plan_pays_after_oop_cap
    assert total == pytest.approx(inp.claim_amount, rel=1e-6, abs=1e-6)


@given(inp=coverage_inputs())
@settings(max_examples=200)
def test_oop_cap_not_applied_when_member_total_within_remaining_oop(inp: CoverageInput) -> None:
    result = calculate_coverage(inp)
    remaining_oop = inp.plan_oop_max - inp.accrued_oop
    if result.member_total <= remaining_oop:
        assert result.oop_cap_applied is False


@given(inp=coverage_inputs())
@settings(max_examples=200)
def test_member_cost_never_exceeds_remaining_oop_max(inp: CoverageInput) -> None:
    result = calculate_coverage(inp)
    remaining_oop = inp.plan_oop_max - inp.accrued_oop
    assert result.member_total_after_oop_cap <= remaining_oop + 1e-9


@given(inp=coverage_inputs())
@settings(max_examples=200)
def test_increasing_accrued_deductible_never_decreases_member_deductible_share(
    inp: CoverageInput,
) -> None:
    """Holding everything else fixed, paying down more deductible up front
    (accrued_deductible closer to plan_deductible) never increases the
    member's applied-to-deductible share for the same claim."""
    baseline = calculate_coverage(inp)
    higher_accrued = min(inp.accrued_deductible + 100.0, inp.plan_deductible)
    bumped_inp = inp.model_copy(update={"accrued_deductible": higher_accrued})
    bumped = calculate_coverage(bumped_inp)
    assert bumped.applied_to_deductible <= baseline.applied_to_deductible + 1e-9
