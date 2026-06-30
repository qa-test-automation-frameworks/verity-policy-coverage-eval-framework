"""Unit tests for the LLM provider layer (mocked litellm + cassette replay)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from verity.cassettes import CassetteLibrary, CassetteMissError, CassettePayload, ReplayToolCall
from verity.config import Provider, Settings
from verity.cost import RunAccumulator
from verity.providers import CompletionResult, LLMProvider


def _mock_response(
    content: str = "Test response",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> MagicMock:
    """Build a minimal mock litellm CompletionResponse."""
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = prompt_tokens
    mock_usage.completion_tokens = completion_tokens
    mock_usage.total_tokens = prompt_tokens + completion_tokens

    mock_message = MagicMock()
    mock_message.content = content
    mock_message.tool_calls = []

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_resp = MagicMock()
    mock_resp.usage = mock_usage
    mock_resp.choices = [mock_choice]
    return mock_resp


_PATCH = "verity.providers.litellm.completion"


@pytest.fixture()
def settings_no_key() -> Settings:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Settings(provider=Provider.zai, model="glm-5.2")


class TestLLMProvider:
    def test_complete_returns_typed_result(self, settings_no_key: Settings) -> None:
        acc = RunAccumulator()
        provider = LLMProvider(settings_no_key, acc)

        with patch(_PATCH, return_value=_mock_response("Hello")) as mock_call:
            result = provider.complete([{"role": "user", "content": "hi"}])

        assert isinstance(result, CompletionResult)
        assert result.content == "Hello"
        assert result.tool_calls == []
        mock_call.assert_called_once()

    def test_cost_accumulated_after_call(self, settings_no_key: Settings) -> None:
        acc = RunAccumulator()
        provider = LLMProvider(settings_no_key, acc)
        mock_resp = _mock_response(prompt_tokens=100, completion_tokens=50)

        with patch(_PATCH, return_value=mock_resp):
            provider.complete([{"role": "user", "content": "test"}])

        assert acc.total_tokens.prompt_tokens == 100
        assert acc.total_tokens.completion_tokens == 50
        assert len(acc.records) == 1

    def test_tools_passed_when_provided(self, settings_no_key: Settings) -> None:
        acc = RunAccumulator()
        provider = LLMProvider(settings_no_key, acc)
        tools: list[dict[str, Any]] = [
            {"type": "function", "function": {"name": "test_fn", "parameters": {}}}
        ]

        with patch(_PATCH, return_value=_mock_response()) as mock_call:
            provider.complete([{"role": "user", "content": "use the tool"}], tools=tools)

        call_kwargs = mock_call.call_args.kwargs
        assert "tools" in call_kwargs
        assert call_kwargs["tools"] == tools

    def test_temperature_override(self, settings_no_key: Settings) -> None:
        acc = RunAccumulator()
        provider = LLMProvider(settings_no_key, acc)

        with patch(_PATCH, return_value=_mock_response()) as mock_call:
            provider.complete([{"role": "user", "content": "hi"}], temperature=0.5)

        assert mock_call.call_args.kwargs["temperature"] == 0.5

    def test_multiple_calls_accumulated(self, settings_no_key: Settings) -> None:
        acc = RunAccumulator()
        provider = LLMProvider(settings_no_key, acc)
        mock_resp = _mock_response(prompt_tokens=50, completion_tokens=20)

        with patch(_PATCH, return_value=mock_resp):
            provider.complete([{"role": "user", "content": "first"}])
            provider.complete([{"role": "user", "content": "second"}])

        assert len(acc.records) == 2
        assert acc.total_tokens.prompt_tokens == 100


class TestCassetteReplay:
    @pytest.fixture()
    def replay_settings(self, tmp_path: Path) -> Settings:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return Settings(
                provider=Provider.zai,
                model="glm-5.2",
                cassette_mode="replay",
                cassette_dir=tmp_path,
            )

    @pytest.fixture()
    def record_settings(self, tmp_path: Path) -> Settings:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return Settings(
                provider=Provider.zai,
                model="glm-5.2",
                cassette_mode="record",
                cassette_dir=tmp_path,
            )

    def _make_payload(self, content: str = "replayed") -> CassettePayload:
        return CassettePayload(
            content=content,
            tool_calls=[],
            prompt_tokens=8,
            completion_tokens=4,
            total_tokens=12,
            model="openai/glm-5.2",
        )

    def test_replay_hit_returns_cassette_content(
        self, replay_settings: Settings, tmp_path: Path
    ) -> None:
        lib = CassetteLibrary(tmp_path)
        acc = RunAccumulator()
        provider = LLMProvider(replay_settings, acc, cassette_library=lib)

        msgs: list[dict[str, Any]] = [{"role": "user", "content": "hi"}]
        from verity.cassettes import request_key

        key = request_key("openai/glm-5.2", msgs, None, 0.0, 2048)
        lib.save(key, self._make_payload("cassette says hello"))

        result = provider.complete(msgs)
        assert result.content == "cassette says hello"
        assert result.raw_response is None  # no live call
        assert len(acc.records) == 1
        assert acc.records[0].usage.prompt_tokens == 8

    def test_replay_miss_raises_cassette_miss_error(
        self, replay_settings: Settings, tmp_path: Path
    ) -> None:
        lib = CassetteLibrary(tmp_path)
        provider = LLMProvider(replay_settings, accumulator=RunAccumulator(), cassette_library=lib)

        with pytest.raises(CassetteMissError):
            provider.complete([{"role": "user", "content": "no cassette here"}])

    def test_record_mode_saves_cassette(self, record_settings: Settings, tmp_path: Path) -> None:
        lib = CassetteLibrary(tmp_path)
        acc = RunAccumulator()
        provider = LLMProvider(record_settings, acc, cassette_library=lib)

        msgs: list[dict[str, Any]] = [{"role": "user", "content": "record me"}]
        with patch(_PATCH, return_value=_mock_response("live result")) as mock_call:
            result = provider.complete(msgs)

        mock_call.assert_called_once()
        assert result.content == "live result"

        from verity.cassettes import request_key

        key = request_key("openai/glm-5.2", msgs, None, 0.0, 2048)
        assert lib.has(key), "Cassette should have been saved after record-mode call"

    def test_replay_with_tool_calls(self, replay_settings: Settings, tmp_path: Path) -> None:
        from verity.cassettes import ReplayFunction, request_key

        lib = CassetteLibrary(tmp_path)
        provider = LLMProvider(replay_settings, RunAccumulator(), cassette_library=lib)

        msgs: list[dict[str, Any]] = [{"role": "user", "content": "calc cost"}]
        key = request_key("openai/glm-5.2", msgs, None, 0.0, 2048)
        tc = ReplayToolCall(
            id="call_fx_001",
            function=ReplayFunction(
                name="coverage_calculator",
                arguments='{"claim_amount": 1000.0}',
            ),
        )
        lib.save(key, CassettePayload("", [tc], 5, 3, 8, "openai/glm-5.2"))

        result = provider.complete(msgs)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].function.name == "coverage_calculator"
