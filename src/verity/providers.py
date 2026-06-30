"""LiteLLM wrapper routing calls through the configured provider (Z.ai / OpenRouter / Together).

Cassette integration: when Settings.cassette_mode is "replay", every completion
request is served from a pre-recorded CassetteLibrary instead of making a live
API call. A cache miss raises CassetteMissError (fail-fast). When mode is
"record", live calls are made and responses are persisted for future replay.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import litellm

from verity.cassettes import (
    CassetteLibrary,
    CassetteMissError,
    CassettePayload,
    ReplayFunction,
    ReplayToolCall,
    request_key,
)
from verity.config import Settings, get_settings
from verity.cost import CallRecord, RunAccumulator, Usage, usage_from_litellm
from verity.tracing import record_call_span


@dataclass
class CompletionResult:
    content: str
    tool_calls: list[Any] = field(default_factory=list)
    raw_response: Any = None
    call_record: CallRecord | None = None


class LLMProvider:
    """Thin typed wrapper over litellm.completion, routing to the configured provider."""

    def __init__(
        self,
        settings: Settings | None = None,
        accumulator: RunAccumulator | None = None,
        cassette_library: CassetteLibrary | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._accumulator = accumulator or RunAccumulator()
        self._cassette = cassette_library

    @property
    def accumulator(self) -> RunAccumulator:
        return self._accumulator

    def _get_cassette_library(self) -> CassetteLibrary:
        if self._cassette is None:
            self._cassette = CassetteLibrary(self._settings.cassette_dir)
        return self._cassette

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        label: str = "",
    ) -> CompletionResult:
        """Send a completion request and return a typed result with cost accounting."""
        s = self._settings
        litellm_model, api_base, api_key = s.resolved_provider()
        temp = temperature if temperature is not None else s.temperature
        max_tok = max_tokens if max_tokens is not None else s.max_tokens
        mode = s.cassette_mode

        if mode == "replay":
            key = request_key(litellm_model, messages, tools, temp, max_tok)
            lib = self._get_cassette_library()
            payload = lib.lookup(key)
            if payload is None:
                raise CassetteMissError(
                    f"No cassette found for key {key!r}. "
                    "Run `make record` to capture responses, then commit cassettes."
                )
            return self._result_from_payload(payload, label)

        # Compute cassette key before live call when recording
        record_key: str | None = None
        record_lib: CassetteLibrary | None = None
        if mode == "record":
            record_key = request_key(litellm_model, messages, tools, temp, max_tok)
            record_lib = self._get_cassette_library()

        # Live call (mode == "off" or mode == "record")
        kwargs: dict[str, Any] = {
            "model": litellm_model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": max_tok,
            "timeout": s.timeout,
            "num_retries": s.retries,
            "api_base": api_base,
        }
        if api_key:
            kwargs["api_key"] = api_key
        if tools:
            kwargs["tools"] = tools

        start = time.monotonic()
        response = litellm.completion(**kwargs)
        latency_ms = (time.monotonic() - start) * 1000

        usage = usage_from_litellm(response)
        record = self._accumulator.log_call(
            model=litellm_model,
            usage=usage,
            latency_ms=latency_ms,
            label=label,
        )
        record_call_span(record)

        choice = response.choices[0]
        message = choice.message
        content: str = message.content or ""
        raw_tool_calls: list[Any] = getattr(message, "tool_calls", None) or []

        if mode == "record" and record_key is not None and record_lib is not None:
            replay_tcs = [
                ReplayToolCall(
                    id=tc.id,
                    function=ReplayFunction(name=tc.function.name, arguments=tc.function.arguments),
                )
                for tc in raw_tool_calls
            ]
            preview = (messages[-1].get("content", "") or "")[:120]
            record_lib.save(
                record_key,
                CassettePayload(
                    content=content,
                    tool_calls=replay_tcs,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                    model=litellm_model,
                ),
                request_preview=preview,
            )

        return CompletionResult(
            content=content,
            tool_calls=raw_tool_calls,
            raw_response=response,
            call_record=record,
        )

    def _result_from_payload(self, payload: CassettePayload, label: str) -> CompletionResult:
        """Reconstruct a CompletionResult from a cassette payload."""
        usage = Usage(
            prompt_tokens=payload.prompt_tokens,
            completion_tokens=payload.completion_tokens,
            total_tokens=payload.total_tokens,
        )
        record = self._accumulator.log_call(
            model=payload.model,
            usage=usage,
            latency_ms=0.0,
            label=label,
        )
        record_call_span(record)
        return CompletionResult(
            content=payload.content,
            tool_calls=payload.tool_calls,  # ReplayToolCall objects — same interface
            raw_response=None,
            call_record=record,
        )
