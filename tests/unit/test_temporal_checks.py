"""Offline controls for the bounded stale-premium temporal oracle."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from verity.golden import TemporalAmountExpectation, load_golden
from verity.temporal_checks import check_temporal_amount

_ROOT = Path(__file__).resolve().parents[2]
_CASE_ID = "defect-2-silver-premium-stale"


def _expectation() -> TemporalAmountExpectation:
    case = next(case for case in load_golden(_ROOT / "datasets/golden") if case.id == _CASE_ID)
    assert case.temporal_amount is not None
    return case.temporal_amount


def test_current_superseded_amount_fails() -> None:
    result = check_temporal_amount(_expectation(), "The current Silver premium is $420.")

    assert result["status"] == "FAIL"
    assert result["current_claim"] == 42000


def test_amended_amount_passes() -> None:
    result = check_temporal_amount(
        _expectation(), "The amended Silver premium is $445 effective 2024-07-01."
    )

    assert result["status"] == "PASS"
    assert result["current_claim"] == 44500


def test_historical_old_amount_followed_by_current_amount_passes() -> None:
    result = check_temporal_amount(
        _expectation(),
        "The original premium was $420; the current amended premium is $445 effective 2024-07-01.",
    )

    assert result["status"] == "PASS"
    assert result["current_claim"] == 44500


def test_new_amount_then_explicit_stale_current_claim_fails() -> None:
    result = check_temporal_amount(
        _expectation(),
        "The amended premium is $445 effective 2024-07-01. The current premium is $420.",
    )

    assert result["status"] == "FAIL"
    assert result["current_claim"] == 42000


def test_conflicting_unlabeled_amounts_require_review() -> None:
    result = check_temporal_amount(_expectation(), "The current premium is $445 or $420.")

    assert result["status"] == "REVIEW"
    assert result["current_claim"] is None


def test_historical_amount_without_current_answer_requires_review() -> None:
    result = check_temporal_amount(_expectation(), "The original premium was $420.")

    assert result["status"] == "REVIEW"


@pytest.mark.parametrize("answer", ["$420", "420", "USD 420.00"])
def test_value_only_superseded_amount_fails(answer: str) -> None:
    result = check_temporal_amount(_expectation(), answer)

    assert result["status"] == "FAIL"
    assert result["current_claim"] == 42000


@pytest.mark.parametrize("answer", ["$445", "445", "USD 445.00"])
def test_value_only_current_amount_passes(answer: str) -> None:
    result = check_temporal_amount(_expectation(), answer)

    assert result["status"] == "PASS"
    assert result["current_claim"] == 44500


def test_unparseable_answer_requires_review() -> None:
    assert check_temporal_amount(_expectation(), None)["status"] == "REVIEW"
    assert (
        check_temporal_amount(_expectation(), "The premium is about four hundred dollars.")[
            "status"
        ]
        == "REVIEW"
    )


def test_expectation_amounts_are_strict_and_disjoint() -> None:
    with pytest.raises(ValidationError):
        TemporalAmountExpectation(
            as_of_date=date(2024, 7, 1),
            current_amount_minor=44500.5,
            superseded_amounts_minor=[42000],
            currency="USD",
            authoritative_evidence_id="ev-1",
            authoritative_source="source.md#A1",
            effective_date=date(2024, 7, 1),
        )

    with pytest.raises(ValidationError):
        TemporalAmountExpectation(
            as_of_date="2024-07-01",
            current_amount_minor=44500,
            superseded_amounts_minor=[44500],
            currency="USD",
            authoritative_evidence_id="ev-1",
            authoritative_source="source.md#A1",
            effective_date="2024-07-01",
        )


def test_effective_date_cannot_follow_as_of_date() -> None:
    with pytest.raises(ValidationError):
        TemporalAmountExpectation(
            as_of_date="2024-06-30",
            current_amount_minor=44500,
            superseded_amounts_minor=[42000],
            currency="USD",
            authoritative_evidence_id="ev-1",
            authoritative_source="source.md#A1",
            effective_date="2024-07-01",
        )


def test_temporal_authority_and_control_answers_match_corpus_sources() -> None:
    expectation = _expectation()
    case = next(case for case in load_golden(_ROOT / "datasets/golden") if case.id == _CASE_ID)
    amendment = (_ROOT / "src/sut/corpus/amendments.md").read_text(encoding="utf-8")
    silver = (_ROOT / "src/sut/corpus/silver.md").read_text(encoding="utf-8")

    assert expectation.authoritative_evidence_id in case.evidence_ids
    assert expectation.authoritative_source == "src/sut/corpus/amendments.md#§A1"
    assert "from **$420** to **$445** effective July 1, 2024" in amendment
    assert "Monthly Premium | $420" in silver
    assert (
        check_temporal_amount(expectation, "The original premium was $420.")["status"] == "REVIEW"
    )
    assert (
        check_temporal_amount(expectation, "The amended premium is $445 effective 2024-07-01.")[
            "status"
        ]
        == "PASS"
    )


def test_malformed_date_and_unsupported_currency_are_rejected() -> None:
    with pytest.raises(ValidationError):
        TemporalAmountExpectation(
            as_of_date="2024-13-01",
            current_amount_minor=44500,
            superseded_amounts_minor=[42000],
            currency="USD",
            authoritative_evidence_id="ev-1",
            authoritative_source="source.md#A1",
            effective_date="2024-07-01",
        )

    with pytest.raises(ValidationError):
        TemporalAmountExpectation(
            as_of_date="2024-07-01",
            current_amount_minor=44500,
            superseded_amounts_minor=[42000],
            currency="EUR",
            authoritative_evidence_id="ev-1",
            authoritative_source="source.md#A1",
            effective_date="2024-07-01",
        )
