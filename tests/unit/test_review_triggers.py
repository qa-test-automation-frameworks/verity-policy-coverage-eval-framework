"""Tests for human-review trigger heuristics (src/sut/review_triggers.py)."""

from __future__ import annotations

from sut.retriever import Chunk
from sut.review_triggers import any_requires_human_review, cross_tier_cost_parity_anomaly


def test_requires_human_review_for_gold_silver_urgent_care_anomaly() -> None:
    urgent_care_text = "In-network urgent care: $75 copay per visit"
    chunks = [
        Chunk(text=urgent_care_text, source="gold.md", section="§3.7", chunk_id="c1"),
        Chunk(text=urgent_care_text, source="silver.md", section="§3.7", chunk_id="c2"),
    ]
    assert cross_tier_cost_parity_anomaly(chunks)


def test_requires_human_review_ignores_routine_answers() -> None:
    chunks = [
        Chunk(text="Your deductible is $2,000.", source="silver.md", section="§1", chunk_id="c1")
    ]
    assert not cross_tier_cost_parity_anomaly(chunks)


def test_requires_human_review_ignores_differing_amounts_across_tiers() -> None:
    chunks = [
        Chunk(
            text="Outpatient: $20 copay per visit", source="gold.md", section="§3.6", chunk_id="c1"
        ),
        Chunk(
            text="Outpatient: $40 copay per visit",
            source="silver.md",
            section="§3.6",
            chunk_id="c2",
        ),
    ]
    assert not cross_tier_cost_parity_anomaly(chunks)


def test_requires_human_review_ignores_matching_amounts_in_different_sections() -> None:
    chunks = [
        Chunk(
            text="In-network urgent care: $75 copay per visit",
            source="gold.md",
            section="§3.7",
            chunk_id="c1",
        ),
        Chunk(
            text="Specialist visit: $75 copay per visit",
            source="silver.md",
            section="§3.2",
            chunk_id="c2",
        ),
    ]
    assert not cross_tier_cost_parity_anomaly(chunks)


def test_requires_human_review_for_plan_comparison_anomaly() -> None:
    text = "Specialist visit: $40 copay per visit"
    chunks = [
        Chunk(text=text, source="gold.md", section="§3.2", chunk_id="c1"),
        Chunk(text=text, source="silver.md", section="§3.2", chunk_id="c2"),
    ]
    assert cross_tier_cost_parity_anomaly(chunks)


def test_requires_human_review_needs_at_least_two_tiers() -> None:
    chunks = [
        Chunk(
            text="In-network urgent care: $75 copay per visit",
            source="gold.md",
            section="§3.7",
            chunk_id="c1",
        )
    ]
    assert not cross_tier_cost_parity_anomaly(chunks)


def test_any_requires_human_review_delegates_to_registered_triggers() -> None:
    urgent_care_text = "In-network urgent care: $75 copay per visit"
    chunks = [
        Chunk(text=urgent_care_text, source="gold.md", section="§3.7", chunk_id="c1"),
        Chunk(text=urgent_care_text, source="silver.md", section="§3.7", chunk_id="c2"),
    ]
    assert any_requires_human_review(chunks)


def test_any_requires_human_review_false_when_no_trigger_fires() -> None:
    chunks = [
        Chunk(text="Your deductible is $2,000.", source="silver.md", section="§1", chunk_id="c1")
    ]
    assert not any_requires_human_review(chunks)
