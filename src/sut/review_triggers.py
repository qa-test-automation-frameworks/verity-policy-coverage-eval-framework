"""Heuristics that flag a response as needing human review.

Each trigger inspects the chunks retrieved for a query and returns True when
it detects a pattern the agent itself cannot safely resolve. Registered in
_TRIGGERS so new heuristics can be added without touching the agent loop.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sut.retriever import Chunk

_DOLLAR_AMOUNT_RE = re.compile(r"\$\d[\d,]*(?:\.\d+)?")
_PLAN_TIER_SOURCES = ("bronze.md", "silver.md", "gold.md")


def cross_tier_cost_parity_anomaly(chunks: list[Chunk]) -> bool:
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


ReviewTrigger = Callable[[list[Chunk]], bool]

_TRIGGERS: tuple[ReviewTrigger, ...] = (cross_tier_cost_parity_anomaly,)


def any_requires_human_review(chunks: list[Chunk]) -> bool:
    """True if any registered review trigger fires for the given chunks."""
    return any(trigger(chunks) for trigger in _TRIGGERS)


@dataclass(frozen=True)
class ReviewItem:
    """Queued response that must be approved before member-facing finalization."""

    id: str
    query: str
    answer: str
    chunk_sources: tuple[str, ...]
    approved: bool = False
    reviewer: str = ""


@dataclass
class ReviewQueue:
    """In-memory review queue for demos and tests.

    Production callers can replace this with a durable store while preserving
    the same submit/approve/finalize contract.
    """

    items: dict[str, ReviewItem] = field(default_factory=dict)

    def submit(self, query: str, answer: str, chunks: list[Chunk]) -> ReviewItem:
        item = ReviewItem(
            id=uuid.uuid4().hex,
            query=query,
            answer=answer,
            chunk_sources=tuple(sorted({chunk.source for chunk in chunks})),
        )
        self.items[item.id] = item
        return item

    def approve(self, item_id: str, reviewer: str) -> ReviewItem:
        item = self.items[item_id]
        approved = ReviewItem(
            id=item.id,
            query=item.query,
            answer=item.answer,
            chunk_sources=item.chunk_sources,
            approved=True,
            reviewer=reviewer,
        )
        self.items[item_id] = approved
        return approved

    def can_finalize(self, item_id: str) -> bool:
        return self.items[item_id].approved


def can_finalize_response(*, requires_human_review: bool, review_item: ReviewItem | None) -> bool:
    """Return True only when review-gated responses have an approval record."""
    if not requires_human_review:
        return True
    return bool(review_item and review_item.approved)
