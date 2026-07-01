"""Unit tests for the deterministic coverage_calculator tool."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sut.tools.coverage_calculator import CoverageInput, calculate_coverage, run_coverage_calculator


def _inp(**kwargs: float) -> CoverageInput:
    defaults: dict[str, float] = {
        "claim_amount": 1000.0,
        "plan_deductible": 2000.0,
        "accrued_deductible": 0.0,
        "plan_oop_max": 6000.0,
        "accrued_oop": 0.0,
        "coinsurance_member": 0.20,
        "copay": 0.0,
    }
    defaults.update(kwargs)
    return CoverageInput(**defaults)


class TestDeductiblePhase:
    def test_full_claim_absorbed_by_deductible(self) -> None:
        result = calculate_coverage(_inp(claim_amount=500.0, accrued_deductible=0.0))
        assert result.applied_to_deductible == 500.0
        assert result.member_coinsurance == 0.0
        assert result.member_total == 500.0
        assert result.plan_pays == 0.0

    def test_partial_deductible_remaining(self) -> None:
        result = calculate_coverage(_inp(claim_amount=3000.0, accrued_deductible=1200.0))
        # remaining deductible = 2000 - 1200 = 800
        assert result.remaining_deductible_before == 800.0
        assert result.applied_to_deductible == 800.0
        # after deductible: 3000 - 800 = 2200 at 20%
        assert result.amount_subject_to_coinsurance == pytest.approx(2200.0)
        assert result.member_coinsurance == pytest.approx(440.0)
        assert result.member_total == pytest.approx(1240.0)

    def test_deductible_already_met(self) -> None:
        result = calculate_coverage(
            _inp(claim_amount=1000.0, accrued_deductible=2000.0, plan_deductible=2000.0)
        )
        assert result.applied_to_deductible == 0.0
        assert result.member_coinsurance == pytest.approx(200.0)
        assert result.member_total == pytest.approx(200.0)


class TestCoinsurance:
    def test_20_percent_coinsurance(self) -> None:
        result = calculate_coverage(
            _inp(
                claim_amount=1000.0,
                accrued_deductible=2000.0,
                plan_deductible=2000.0,
                coinsurance_member=0.20,
            )
        )
        assert result.member_coinsurance == pytest.approx(200.0)
        assert result.plan_pays_after_oop_cap == pytest.approx(800.0)

    def test_10_percent_coinsurance_gold(self) -> None:
        result = calculate_coverage(
            _inp(
                claim_amount=2000.0,
                plan_deductible=750.0,
                accrued_deductible=750.0,
                plan_oop_max=4000.0,
                coinsurance_member=0.10,
            )
        )
        assert result.member_coinsurance == pytest.approx(200.0)
        assert result.plan_pays_after_oop_cap == pytest.approx(1800.0)

    def test_40_percent_coinsurance_bronze(self) -> None:
        result = calculate_coverage(
            _inp(
                claim_amount=1000.0,
                plan_deductible=4000.0,
                accrued_deductible=4000.0,
                plan_oop_max=8000.0,
                coinsurance_member=0.40,
            )
        )
        assert result.member_coinsurance == pytest.approx(400.0)


class TestCopay:
    def test_copay_replaces_coinsurance(self) -> None:
        result = calculate_coverage(
            _inp(
                claim_amount=200.0,
                accrued_deductible=2000.0,
                plan_deductible=2000.0,
                copay=30.0,
                coinsurance_member=0.0,
            )
        )
        assert result.member_copay == 30.0
        assert result.member_coinsurance == 0.0
        assert result.member_total == 30.0

    def test_copay_capped_at_claim_amount(self) -> None:
        result = calculate_coverage(
            _inp(
                claim_amount=20.0,
                accrued_deductible=2000.0,
                plan_deductible=2000.0,
                copay=30.0,
                coinsurance_member=0.0,
            )
        )
        assert result.member_copay == 20.0


class TestOopMax:
    def test_oop_cap_applied(self) -> None:
        result = calculate_coverage(
            _inp(
                claim_amount=10000.0,
                plan_deductible=2000.0,
                accrued_deductible=2000.0,
                plan_oop_max=6000.0,
                accrued_oop=5800.0,
                coinsurance_member=0.20,
            )
        )
        assert result.oop_cap_applied is True
        assert result.member_total_after_oop_cap == pytest.approx(200.0)

    def test_oop_not_capped_when_below_max(self) -> None:
        result = calculate_coverage(
            _inp(
                claim_amount=100.0,
                plan_deductible=2000.0,
                accrued_deductible=2000.0,
                plan_oop_max=6000.0,
                accrued_oop=0.0,
                coinsurance_member=0.20,
            )
        )
        assert result.oop_cap_applied is False
        assert result.member_total_after_oop_cap == pytest.approx(20.0)


class TestValidation:
    def test_zero_claim_raises(self) -> None:
        with pytest.raises(ValidationError):
            _inp(claim_amount=0.0)

    def test_negative_claim_raises(self) -> None:
        with pytest.raises(ValidationError):
            _inp(claim_amount=-100.0)

    def test_accrued_deductible_exceeds_plan_raises(self) -> None:
        with pytest.raises(ValidationError):
            _inp(plan_deductible=2000.0, accrued_deductible=2500.0)

    def test_accrued_oop_exceeds_plan_raises(self) -> None:
        with pytest.raises(ValidationError):
            _inp(plan_oop_max=6000.0, accrued_oop=6001.0)

    def test_unexpected_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            _inp(unexpected_field=1.0)


class TestRunCoverageCalculator:
    def test_round_trip_via_dict(self) -> None:
        args = {
            "claim_amount": 3500.0,
            "plan_deductible": 2000.0,
            "accrued_deductible": 1200.0,
            "plan_oop_max": 6000.0,
            "accrued_oop": 0.0,
            "coinsurance_member": 0.20,
        }
        result = run_coverage_calculator(args)
        # Matches the worked example in amendments.md §A3
        assert result["applied_to_deductible"] == pytest.approx(800.0)
        assert result["member_coinsurance"] == pytest.approx(540.0)
        assert result["member_total"] == pytest.approx(1340.0)

    def test_unknown_argument_raises(self) -> None:
        args = {
            "claim_amount": 500.0,
            "plan_deductible": 2000.0,
            "accrued_deductible": 0.0,
            "plan_oop_max": 6000.0,
            "accrued_oop": 0.0,
            "coinsurance_member": 0.20,
            "unexpected_field": "sneaky",
        }
        with pytest.raises(ValidationError):
            run_coverage_calculator(args)


class TestToolSchema:
    def test_schema_disallows_additional_properties(self) -> None:
        from sut.tools.coverage_calculator import COVERAGE_CALCULATOR_SCHEMA

        assert COVERAGE_CALCULATOR_SCHEMA["function"]["parameters"]["additionalProperties"] is False
