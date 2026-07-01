"""Tests proving agent fails closed for unknown member IDs."""

from __future__ import annotations

import pytest

from sut.agent import _PLAN_PARAMS, _load_members, _requires_human_review


def test_known_member_ids_are_loadable() -> None:
    members = _load_members()
    assert members
    for member_id, member in members.items():
        assert member["member_id"] == member_id


def test_unknown_member_raises_key_error() -> None:
    members = _load_members()
    with pytest.raises(KeyError, match="MBR-UNKNOWN"):
        _ = members["MBR-UNKNOWN"]


def test_no_member_data_returned_for_unknown_id() -> None:
    members = _load_members()
    result = members.get("MBR-DOES-NOT-EXIST")
    assert result is None


def test_unknown_member_id_does_not_fall_back_to_first_member() -> None:
    members = _load_members()
    first_member_id = next(iter(members))
    unknown_id = "MBR-NOTREAL"
    assert unknown_id not in members
    result = members.get(unknown_id)
    assert result is None
    assert result != members[first_member_id]


def test_requires_human_review_for_gold_silver_urgent_care_anomaly() -> None:
    assert _requires_human_review(
        "Does Gold have a lower urgent care copay than Silver?",
        "Gold and Silver have the same $75 urgent care copay.",
    )


def test_requires_human_review_ignores_routine_answers() -> None:
    assert not _requires_human_review("What is my deductible?", "Your deductible is $2,000.")


def test_plan_parameters_match_corpus_overview() -> None:
    expected = {
        "bronze": {"plan_deductible": 4000.0, "plan_oop_max": 8000.0, "coinsurance_member": 0.40},
        "silver": {"plan_deductible": 2000.0, "plan_oop_max": 6000.0, "coinsurance_member": 0.20},
        "gold": {"plan_deductible": 750.0, "plan_oop_max": 4000.0, "coinsurance_member": 0.10},
    }
    assert expected == _PLAN_PARAMS


def test_requires_human_review_for_plan_comparison_anomaly() -> None:
    assert _requires_human_review(
        "Is Gold cheaper than Silver for this service?",
        "Gold and Silver have the same $40 copay for this service.",
    )
