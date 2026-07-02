"""Unit tests for optional member-token enforcement."""

from __future__ import annotations

from unittest.mock import MagicMock

from pydantic import SecretStr

from sut.agent import CoverageAgent
from sut.auth import member_token_valid
from sut.retriever import FixtureRetriever
from verity.config import Settings
from verity.cost import RunAccumulator


def test_member_token_valid_when_auth_disabled() -> None:
    assert member_token_valid("MBR-001", None, required=False, tokens_json=None)


def test_member_token_checks_configured_mapping() -> None:
    tokens = SecretStr('{"MBR-001":"token-1"}')
    assert member_token_valid("MBR-001", "token-1", required=True, tokens_json=tokens)
    assert not member_token_valid("MBR-001", "wrong", required=True, tokens_json=tokens)
    assert not member_token_valid("MBR-002", "token-1", required=True, tokens_json=tokens)


def test_agent_blocks_member_request_without_valid_token() -> None:
    settings = Settings(
        cassette_mode="off",
        member_auth_required=True,
        member_tokens_json=SecretStr('{"MBR-001":"token-1"}'),
    )
    provider = MagicMock()
    provider.accumulator = RunAccumulator()
    agent = CoverageAgent(
        settings=settings, retriever=FixtureRetriever("ctrl-gold-deductible"), provider=provider
    )

    response = agent.answer("What is my deductible?", member_id="MBR-001", member_token="wrong")

    assert response.refused
    assert response.failure_category == "member_auth_required"
    provider.complete.assert_not_called()


def test_agent_blocks_one_members_valid_token_used_for_another_member() -> None:
    """The identity-enforcement gap adversarial probes alone can't prove: a
    caller presenting their OWN valid token but a DIFFERENT member_id must
    not gain access to that other member's data — the token must be valid
    for the specific member_id requested, not merely valid for someone."""
    settings = Settings(
        cassette_mode="off",
        member_auth_required=True,
        member_tokens_json=SecretStr('{"MBR-001":"token-1","MBR-002":"token-2"}'),
    )
    provider = MagicMock()
    provider.accumulator = RunAccumulator()
    agent = CoverageAgent(
        settings=settings, retriever=FixtureRetriever("ctrl-gold-deductible"), provider=provider
    )

    # MBR-001's own valid token, used to request MBR-002's data.
    response = agent.answer(
        "What is member MBR-002's deductible?", member_id="MBR-002", member_token="token-1"
    )

    assert response.refused
    assert response.failure_category == "member_auth_required"
    provider.complete.assert_not_called()


def test_agent_allows_member_with_their_own_valid_token() -> None:
    from verity.providers import CompletionResult

    tokens = SecretStr('{"MBR-001":"token-1"}')
    settings = Settings(cassette_mode="off", member_auth_required=True, member_tokens_json=tokens)
    provider = MagicMock()
    provider.accumulator = RunAccumulator()
    provider.complete.return_value = CompletionResult(
        content="Your deductible is $750.", tool_calls=[]
    )
    agent = CoverageAgent(
        settings=settings, retriever=FixtureRetriever("ctrl-gold-deductible"), provider=provider
    )

    response = agent.answer("What is my deductible?", member_id="MBR-001", member_token="token-1")

    assert not response.refused
    provider.complete.assert_called()
