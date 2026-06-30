"""VCR-style cassette record/replay library for hermetic LLM testing.

Cassettes are stored as pretty-printed JSON files keyed by a SHA-256 hash of
the canonical request (model + messages + tools + temperature + max_tokens).
This makes replay robust to call order and independent of file naming.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class CassetteMissError(KeyError):
    """Raised in replay mode when no cassette exists for the request key.

    Fail-fast semantics: a missing cassette in CI means an unanticipated live
    call is about to be made, which violates the Tier-1 zero-live-calls contract.
    """


@dataclass(frozen=True)
class ReplayFunction:
    name: str
    arguments: str  # raw JSON string, same as litellm's tc.function.arguments


@dataclass(frozen=True)
class ReplayToolCall:
    id: str
    function: ReplayFunction


@dataclass(frozen=True)
class CassettePayload:
    content: str
    tool_calls: list[ReplayToolCall]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str


@dataclass
class CassetteLibrary:
    """Manages cassette files on disk with an in-memory LRU cache."""

    path: Path
    _cache: dict[str, CassettePayload] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)

    def _key_file(self, key: str) -> Path:
        return self.path / f"{key}.json"

    def has(self, key: str) -> bool:
        return key in self._cache or self._key_file(key).exists()

    def lookup(self, key: str) -> CassettePayload | None:
        if key in self._cache:
            return self._cache[key]
        f = self._key_file(key)
        if not f.exists():
            return None
        raw: Any = json.loads(f.read_text())
        tcs = [
            ReplayToolCall(
                id=tc["id"],
                function=ReplayFunction(
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                ),
            )
            for tc in raw.get("tool_calls", [])
        ]
        payload = CassettePayload(
            content=raw["content"],
            tool_calls=tcs,
            prompt_tokens=raw["usage"]["prompt_tokens"],
            completion_tokens=raw["usage"]["completion_tokens"],
            total_tokens=raw["usage"]["total_tokens"],
            model=raw["model"],
        )
        self._cache[key] = payload
        return payload

    def save(self, key: str, payload: CassettePayload, request_preview: str = "") -> None:
        """Persist a cassette to disk and cache it in memory."""
        data: dict[str, Any] = {
            "_request_preview": request_preview,
            "model": payload.model,
            "content": payload.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in payload.tool_calls
            ],
            "usage": {
                "prompt_tokens": payload.prompt_tokens,
                "completion_tokens": payload.completion_tokens,
                "total_tokens": payload.total_tokens,
            },
        }
        self._key_file(key).write_text(json.dumps(data, indent=2) + "\n")
        self._cache[key] = payload


def request_key(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    temperature: float,
    max_tokens: int,
) -> str:
    """Compute a stable 32-hex-char SHA-256 key for a completion request.

    Canonical form: JSON with sorted keys, so call-order and dict insertion
    order do not affect the hash.
    """
    payload: dict[str, Any] = {
        "max_tokens": max_tokens,
        "messages": messages,
        "model": model,
        "temperature": temperature,
        "tools": tools or [],
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]
