"""Tests for CoverageAgent's non-None provider/retriever accessor properties."""

from __future__ import annotations

import pytest

from sut.agent import CoverageAgent
from verity.config import Settings


def _agent() -> CoverageAgent:
    return CoverageAgent(settings=Settings(cassette_mode="off"))


def test_llm_provider_returns_provider_when_set() -> None:
    agent = _agent()
    assert agent._llm_provider is agent.provider


def test_llm_provider_raises_runtime_error_when_none() -> None:
    agent = _agent()
    agent.provider = None
    with pytest.raises(RuntimeError, match=r"CoverageAgent\.provider is None"):
        _ = agent._llm_provider


def test_chunk_retriever_returns_retriever_when_set() -> None:
    agent = _agent()
    assert agent._chunk_retriever is agent.retriever


def test_chunk_retriever_raises_runtime_error_when_none() -> None:
    agent = _agent()
    agent.retriever = None
    with pytest.raises(RuntimeError, match=r"CoverageAgent\.retriever is None"):
        _ = agent._chunk_retriever
