"""Unit tests for the LLM provider layer (mocked litellm + cassette replay)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from verity.cassettes import CassetteLibrary, CassetteMissError, CassettePayload, ReplayToolCall
from verity.config import Provider, Settings
from verity.cost import RunAccumulator
from verity.providers import (
    RATE_LIMIT_STOP_THRESHOLD,
    CompletionResult,
    LLMProvider,
    ProviderRateLimitCircuitOpenError,
)


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


_PATCH = "verity.providers._litellm_completion"


@pytest.fixture()
def settings_no_key() -> Settings:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Settings(provider=Provider.zai, model="glm-4.5")


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
        assert len(acc.requests) == 1
        assert acc.requests[0].status == "succeeded"
        assert acc.records[0].request_id == acc.requests[0].request_id

    def test_failed_request_is_recorded_without_error_text(self, settings_no_key: Settings) -> None:
        acc = RunAccumulator()
        provider = LLMProvider(settings_no_key, acc)

        with (
            patch(_PATCH, side_effect=RuntimeError("sensitive provider response")),
            pytest.raises(RuntimeError, match="sensitive provider response"),
        ):
            provider.complete([{"role": "user", "content": "private prompt"}])

        assert len(acc.requests) == 1
        event = acc.requests[0]
        assert event.status == "failed"
        assert event.error_type == "RuntimeError"
        assert event.usage is None
        assert not hasattr(event, "error_message")
        assert acc.records == []

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
        assert call_kwargs["_skip_mcp_handler"] is True

    def test_mcp_handler_is_not_skipped_for_plain_completion(
        self, settings_no_key: Settings
    ) -> None:
        provider = LLMProvider(settings_no_key)

        with patch(_PATCH, return_value=_mock_response()) as mock_call:
            provider.complete([{"role": "user", "content": "hi"}])

        assert "_skip_mcp_handler" not in mock_call.call_args.kwargs

    def test_structured_output_options_are_passed_to_litellm(
        self, settings_no_key: Settings
    ) -> None:
        provider = LLMProvider(settings_no_key)
        response_format = {"type": "json_object"}
        extra_body = {"chat_template_kwargs": {"enable_thinking": False}}

        with patch(_PATCH, return_value=_mock_response()) as mock_call:
            provider.complete(
                [{"role": "user", "content": "score this"}],
                response_format=response_format,
                extra_body=extra_body,
            )

        assert mock_call.call_args.kwargs["response_format"] == response_format
        assert mock_call.call_args.kwargs["extra_body"] == extra_body

    def test_temperature_override(self, settings_no_key: Settings) -> None:
        acc = RunAccumulator()
        provider = LLMProvider(settings_no_key, acc)

        with patch(_PATCH, return_value=_mock_response()) as mock_call:
            provider.complete([{"role": "user", "content": "hi"}], temperature=0.5)

        assert mock_call.call_args.kwargs["temperature"] == 0.5

    def test_none_tool_calls_normalized_to_empty_list(self, settings_no_key: Settings) -> None:
        """litellm returns message.tool_calls=None (not []) when no tool was invoked.

        This is a contract test against that actual response shape, not the
        convenience default set by _mock_response() elsewhere in this file.
        """
        acc = RunAccumulator()
        provider = LLMProvider(settings_no_key, acc)
        mock_resp = _mock_response("no tool needed")
        mock_resp.choices[0].message.tool_calls = None

        with patch(_PATCH, return_value=mock_resp):
            result = provider.complete([{"role": "user", "content": "hi"}])

        assert result.tool_calls == []

    def test_none_content_normalized_to_empty_string(self, settings_no_key: Settings) -> None:
        """litellm returns message.content=None on tool-call-only turns."""
        acc = RunAccumulator()
        provider = LLMProvider(settings_no_key, acc)
        mock_resp = _mock_response()
        mock_resp.choices[0].message.content = None

        with patch(_PATCH, return_value=mock_resp):
            result = provider.complete([{"role": "user", "content": "hi"}])

        assert result.content == ""

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
                model="glm-4.5",
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
                model="glm-4.5",
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
            model="openai/glm-4.5",
        )

    def test_replay_hit_returns_cassette_content(
        self, replay_settings: Settings, tmp_path: Path
    ) -> None:
        lib = CassetteLibrary(tmp_path)
        acc = RunAccumulator()
        provider = LLMProvider(replay_settings, acc, cassette_library=lib)

        msgs: list[dict[str, Any]] = [{"role": "user", "content": "hi"}]
        from verity.cassettes import request_key

        key = request_key("openai/glm-4.5", msgs, None, 0.0, 2048)
        lib.save(key, self._make_payload("cassette says hello"))

        result = provider.complete(msgs)
        assert result.content == "cassette says hello"
        assert result.raw_response is None  # no live call
        assert len(acc.records) == 1
        assert acc.records[0].usage.prompt_tokens == 8

    def test_structured_judge_options_replay_legacy_cassette(
        self, replay_settings: Settings, tmp_path: Path
    ) -> None:
        from verity.cassettes import request_key

        lib = CassetteLibrary(tmp_path)
        provider = LLMProvider(replay_settings, cassette_library=lib)
        messages: list[dict[str, Any]] = [{"role": "user", "content": "score this"}]
        legacy_key = request_key("openai/glm-4.5", messages, None, 0.0, 2048)
        lib.save(legacy_key, self._make_payload("legacy JSON response"))

        result = provider.complete(
            messages,
            response_format={"type": "json_object"},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

        assert result.content == "legacy JSON response"
        assert result.raw_response is None

    def test_tool_request_replays_legacy_follow_up_without_advertised_tools(
        self, replay_settings: Settings, tmp_path: Path
    ) -> None:
        from verity.cassettes import request_key

        lib = CassetteLibrary(tmp_path)
        provider = LLMProvider(replay_settings, cassette_library=lib)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "", "tool_calls": []},
            {"role": "tool", "tool_call_id": "call_1", "content": "result"},
        ]
        legacy_key = request_key("openai/glm-4.5", messages, None, 0.0, 2048)
        lib.save(legacy_key, self._make_payload("legacy follow-up"))
        tools = [{"type": "function", "function": {"name": "tool", "parameters": {}}}]

        result = provider.complete(messages, tools=tools)

        assert result.content == "legacy follow-up"
        assert result.raw_response is None

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

        key = request_key("openai/glm-4.5", msgs, None, 0.0, 2048)
        assert lib.has(key), "Cassette should have been saved after record-mode call"

    def test_replay_with_tool_calls(self, replay_settings: Settings, tmp_path: Path) -> None:
        from verity.cassettes import ReplayFunction, request_key

        lib = CassetteLibrary(tmp_path)
        provider = LLMProvider(replay_settings, RunAccumulator(), cassette_library=lib)

        msgs: list[dict[str, Any]] = [{"role": "user", "content": "calc cost"}]
        key = request_key("openai/glm-4.5", msgs, None, 0.0, 2048)
        tc = ReplayToolCall(
            id="call_fx_001",
            function=ReplayFunction(
                name="coverage_calculator",
                arguments='{"claim_amount": 1000.0}',
            ),
        )
        lib.save(key, CassettePayload("", [tc], 5, 3, 8, "openai/glm-4.5"))

        result = provider.complete(msgs)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].function.name == "coverage_calculator"


def _openai_api_error_type() -> type[Exception]:
    import openai

    return openai.APIError


def _quota_error(status_code: int) -> Exception:
    import httpx
    import openai

    request = httpx.Request("POST", "https://api.example.test/v1/chat/completions")
    response = httpx.Response(status_code, request=request)
    return openai.APIStatusError("insufficient credits", response=response, body=None)


class TestKeyFallback:
    """The primary key retries once against a secondary key on 402/429 only."""

    @pytest.fixture()
    def settings_with_fallback(self) -> Settings:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return Settings(
                _env_file=None,
                provider=Provider.openrouter,
                model="openai/gpt-4o-mini",
                openrouter_api_key="primary-key",
                openrouter_api_key_2="fallback-key",
            )

    def test_retries_with_fallback_key_on_402(self, settings_with_fallback: Settings) -> None:
        acc = RunAccumulator()
        provider = LLMProvider(settings_with_fallback, acc)

        with patch(
            _PATCH,
            side_effect=[_quota_error(402), _mock_response("recovered")],
        ) as mock_call:
            result = provider.complete([{"role": "user", "content": "hi"}])

        assert result.content == "recovered"
        assert mock_call.call_count == 2
        assert mock_call.call_args_list[0].kwargs["api_key"] == "primary-key"
        assert mock_call.call_args_list[1].kwargs["api_key"] == "fallback-key"
        assert [event.status for event in acc.requests] == ["failed", "succeeded"]
        assert [event.http_status for event in acc.requests] == [402, None]

    def test_retries_with_fallback_key_on_429(self, settings_with_fallback: Settings) -> None:
        provider = LLMProvider(settings_with_fallback, RunAccumulator())

        with patch(
            _PATCH,
            side_effect=[_quota_error(429), _mock_response("recovered")],
        ):
            result = provider.complete([{"role": "user", "content": "hi"}])

        assert result.content == "recovered"

    def test_does_not_retry_other_status_codes(self, settings_with_fallback: Settings) -> None:
        provider = LLMProvider(settings_with_fallback, RunAccumulator())

        with (
            patch(_PATCH, side_effect=_quota_error(500)) as mock_call,
            pytest.raises(_openai_api_error_type()),
        ):
            provider.complete([{"role": "user", "content": "hi"}])

        mock_call.assert_called_once()

    def test_raises_original_error_when_no_fallback_configured(
        self, settings_no_key: Settings
    ) -> None:
        provider = LLMProvider(settings_no_key, RunAccumulator())

        with (
            patch(_PATCH, side_effect=_quota_error(402)) as mock_call,
            pytest.raises(_openai_api_error_type()),
        ):
            provider.complete([{"role": "user", "content": "hi"}])

        mock_call.assert_called_once()


class TestRateLimitCircuitBreaker:
    def test_stops_after_five_429_responses_without_sending_a_sixth(
        self, settings_no_key: Settings
    ) -> None:
        accumulator = RunAccumulator()
        provider = LLMProvider(settings_no_key, accumulator)
        rate_limit = _quota_error(429)

        with patch(_PATCH, side_effect=rate_limit) as mock_call:
            for request_number in range(1, RATE_LIMIT_STOP_THRESHOLD):
                with pytest.raises(_openai_api_error_type()):
                    provider.complete([{"role": "user", "content": f"request {request_number}"}])

            with pytest.raises(ProviderRateLimitCircuitOpenError, match="opened after 5 HTTP 429"):
                provider.complete([{"role": "user", "content": "fifth request"}])

            with pytest.raises(ProviderRateLimitCircuitOpenError, match="open after 5 HTTP 429"):
                provider.complete([{"role": "user", "content": "must not be sent"}])

        assert mock_call.call_count == RATE_LIMIT_STOP_THRESHOLD
        assert accumulator.rate_limit_responses == RATE_LIMIT_STOP_THRESHOLD
        assert [event.http_status for event in accumulator.requests] == [
            429
        ] * RATE_LIMIT_STOP_THRESHOLD
        assert all(event.status == "failed" for event in accumulator.requests)

    def test_nvidia_uses_shared_rolling_limiter_and_disables_sdk_retries(self) -> None:
        import warnings
        from unittest.mock import MagicMock

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            settings = Settings(
                _env_file=None,
                provider=Provider.nvidia,
                model="nvidia/nemotron-3.5-lightning-30b-a3b",
                nvidia_api_key="test-key",
                retries=3,
            )
        accumulator = RunAccumulator()
        limiter = MagicMock()
        limiter.acquire.return_value = 0.25
        accumulator.nvidia_rate_limiter = limiter
        provider = LLMProvider(settings, accumulator)

        with patch(_PATCH, return_value=_mock_response()) as mock_call:
            provider.complete([{"role": "user", "content": "hello"}])

        limiter.acquire.assert_called_once_with()
        assert mock_call.call_args.kwargs["max_retries"] == 0
        assert accumulator.requests[0].rate_limit_wait_ms == 250.0
