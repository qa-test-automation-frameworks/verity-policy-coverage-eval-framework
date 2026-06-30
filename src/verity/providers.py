"""LiteLLM wrapper routing calls through the configured provider (Z.ai / OpenRouter / Together)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import litellm

from verity.config import Settings, get_settings
from verity.cost import CallRecord, RunAccumulator, usage_from_litellm


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
    ) -> None:
        self._settings = settings or get_settings()
        self._accumulator = accumulator or RunAccumulator()

    @property
    def accumulator(self) -> RunAccumulator:
        return self._accumulator

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

        kwargs: dict[str, Any] = {
            "model": litellm_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else s.temperature,
            "max_tokens": max_tokens if max_tokens is not None else s.max_tokens,
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

        choice = response.choices[0]
        message = choice.message
        content: str = message.content or ""
        raw_tool_calls: list[Any] = getattr(message, "tool_calls", None) or []

        return CompletionResult(
            content=content,
            tool_calls=raw_tool_calls,
            raw_response=response,
            call_record=record,
        )
