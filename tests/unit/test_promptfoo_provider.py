"""Unit tests for the promptfoo custom provider wrapper."""

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar

import promptfoo.provider as promptfoo_provider


class _FakeSettings:
    seen_modes: ClassVar[list[str]] = []

    def __init__(self, *, cassette_mode: str) -> None:
        self.cassette_mode = cassette_mode
        self.seen_modes.append(cassette_mode)


class _FakeRetriever:
    pass


class _FakeProvider:
    def __init__(self, settings: _FakeSettings, accumulator: object) -> None:
        self.settings = settings
        self.accumulator = accumulator


class _FakeAgent:
    def __init__(self, *, settings: _FakeSettings, retriever: object, provider: object) -> None:
        self.settings = settings
        self.retriever = retriever
        self.provider = provider

    def answer(self, prompt: str, member_id: str) -> SimpleNamespace:
        return SimpleNamespace(answer=f"answered {member_id}: {prompt}")


def test_call_api_defaults_to_supported_cassette_mode(monkeypatch) -> None:
    _FakeSettings.seen_modes = []
    monkeypatch.delenv("VERITY_CASSETTE_MODE", raising=False)
    monkeypatch.setattr(promptfoo_provider, "Settings", _FakeSettings)
    monkeypatch.setattr(promptfoo_provider, "PolicyRetriever", _FakeRetriever)
    monkeypatch.setattr(promptfoo_provider, "LLMProvider", _FakeProvider)
    monkeypatch.setattr(promptfoo_provider, "CoverageAgent", _FakeAgent)

    result = promptfoo_provider.call_api("hello", {"config": {"member_id": "MBR-123"}}, {})

    assert _FakeSettings.seen_modes == ["off"]
    assert result["output"] == "answered MBR-123: hello"
    assert result["tokenUsage"] == {"total": 0, "prompt": 0, "completion": 0}


def test_call_api_serializes_token_usage(monkeypatch) -> None:
    class _CountingProvider(_FakeProvider):
        def __init__(self, settings: _FakeSettings, accumulator: object) -> None:
            super().__init__(settings, accumulator)
            accumulator.log_call(
                model="test-model",
                usage=promptfoo_provider.RunAccumulator().total_tokens.__class__(
                    prompt_tokens=7,
                    completion_tokens=5,
                    total_tokens=12,
                ),
                latency_ms=1.0,
                label="provider-smoke",
            )

    _FakeSettings.seen_modes = []
    monkeypatch.setenv("VERITY_CASSETTE_MODE", "replay")
    monkeypatch.setattr(promptfoo_provider, "Settings", _FakeSettings)
    monkeypatch.setattr(promptfoo_provider, "PolicyRetriever", _FakeRetriever)
    monkeypatch.setattr(promptfoo_provider, "LLMProvider", _CountingProvider)
    monkeypatch.setattr(promptfoo_provider, "CoverageAgent", _FakeAgent)

    result = promptfoo_provider.call_api("hello", {}, {})

    assert _FakeSettings.seen_modes == ["replay"]
    assert result["tokenUsage"] == {"total": 12, "prompt": 7, "completion": 5}
