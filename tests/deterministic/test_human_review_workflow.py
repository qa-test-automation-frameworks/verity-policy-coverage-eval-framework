"""Tier-1: human-review workflow enforcement — a review-required answer must
not be deliverable until an explicit approval is recorded.

review_triggers.py's ReviewQueue/can_finalize_response existed as
infrastructure but CoverageAgent never called it — requires_human_review was
only a flag on the response, with nothing stopping a caller from treating the
answer as final immediately. This proves CoverageAgent.deliver() actually
enforces the gate: pending by default, blocked until approve_review() is
called, and returns the real answer only after approval.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sut.agent import CoverageAgent, PendingReviewError
from sut.retriever import FixtureRetriever
from verity.cassettes import CassetteLibrary
from verity.config import Settings
from verity.cost import RunAccumulator
from verity.golden import load_golden
from verity.providers import LLMProvider

pytestmark = pytest.mark.deterministic

_CASSETTE_DIR = Path("datasets/cassettes")
_REVIEW_CASE_ID = "defect-4-urgent-care-contradiction"
_CASE = next(c for c in load_golden(Path("datasets/golden")) if c.id == _REVIEW_CASE_ID)


def _make_agent(settings: Settings) -> CoverageAgent:
    lib = CassetteLibrary(_CASSETTE_DIR)
    retriever = FixtureRetriever(_CASE.id)
    provider = LLMProvider(settings, RunAccumulator(), cassette_library=lib)
    return CoverageAgent(settings=settings, retriever=retriever, provider=provider)


class TestHumanReviewWorkflow:
    def test_review_required_response_has_a_queued_item(self, _settings: Settings) -> None:
        agent = _make_agent(_settings)
        response = agent.answer(_CASE.query, member_id=_CASE.member_id)
        assert response.requires_human_review
        assert response.review_item_id
        assert response.review_item_id in agent.review_queue.items

    def test_deliver_blocks_before_approval(self, _settings: Settings) -> None:
        agent = _make_agent(_settings)
        response = agent.answer(_CASE.query, member_id=_CASE.member_id)
        with pytest.raises(PendingReviewError):
            agent.deliver(response)

    def test_deliver_succeeds_after_approval(self, _settings: Settings) -> None:
        agent = _make_agent(_settings)
        response = agent.answer(_CASE.query, member_id=_CASE.member_id)
        agent.approve_review(response.review_item_id, reviewer="qa-lead")
        assert agent.deliver(response) == response.answer

    def test_deliver_does_not_gate_non_review_responses(self, _settings: Settings) -> None:
        lib = CassetteLibrary(_CASSETTE_DIR)
        clean_case_id = "ctrl-gold-deductible"
        clean_case = next(c for c in load_golden(Path("datasets/golden")) if c.id == clean_case_id)
        retriever = FixtureRetriever(clean_case_id)
        provider = LLMProvider(_settings, RunAccumulator(), cassette_library=lib)
        agent = CoverageAgent(settings=_settings, retriever=retriever, provider=provider)

        response = agent.answer(clean_case.query, member_id=clean_case.member_id)

        assert not response.requires_human_review
        assert response.review_item_id == ""
        assert agent.deliver(response) == response.answer

    def test_unknown_review_item_id_still_blocks(self, _settings: Settings) -> None:
        """Corrupting/forging a review_item_id must not bypass the gate —
        an unrecognized id is treated as unapproved, not as trusted input."""
        agent = _make_agent(_settings)
        response = agent.answer(_CASE.query, member_id=_CASE.member_id)
        forged = response.model_copy(update={"review_item_id": "not-a-real-id"})
        with pytest.raises(PendingReviewError):
            agent.deliver(forged)

    def test_approving_wrong_item_id_does_not_unblock(self, _settings: Settings) -> None:
        agent = _make_agent(_settings)
        response = agent.answer(_CASE.query, member_id=_CASE.member_id)
        other = agent.review_queue.submit("other query", "other answer", [])
        agent.approve_review(other.id, reviewer="qa-lead")
        with pytest.raises(PendingReviewError):
            agent.deliver(response)
