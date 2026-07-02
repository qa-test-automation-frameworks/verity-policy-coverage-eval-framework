"""Tests for human-review trigger heuristics (src/sut/review_triggers.py)."""

from __future__ import annotations

from sut.retriever import Chunk
from sut.review_triggers import ReviewQueue, any_requires_human_review, can_finalize_response, cross_tier_cost_parity_anomaly


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


def test_review_queue_blocks_finalize_until_approved() -> None:
    chunks = [Chunk(text="In-network urgent care: $75 copay", source="gold.md", section="§3.7", chunk_id="c1")]
    queue = ReviewQueue()
    item = queue.submit("Is Gold cheaper?", "Gold and Silver match at $75.", chunks)

    assert not queue.can_finalize(item.id)
    assert not can_finalize_response(requires_human_review=True, review_item=item)

    approved = queue.approve(item.id, reviewer="policy-reviewer")
    assert queue.can_finalize(item.id)
    assert can_finalize_response(requires_human_review=True, review_item=approved)


def test_routine_response_can_finalize_without_review_item() -> None:
    assert can_finalize_response(requires_human_review=False, review_item=None)
