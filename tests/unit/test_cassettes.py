"""Unit tests for the cassette record/replay library."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from verity.cassettes import (
    CassetteLibrary,
    CassetteMissError,
    CassettePayload,
    ReplayFunction,
    ReplayToolCall,
    request_key,
)


def _payload(
    content: str = "Test response",
    tool_calls: list[ReplayToolCall] | None = None,
    prompt: int = 10,
    completion: int = 5,
    model: str = "openai/glm-4.5",
) -> CassettePayload:
    return CassettePayload(
        content=content,
        tool_calls=tool_calls or [],
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        model=model,
    )


class TestRequestKey:
    def test_deterministic(self) -> None:
        msgs: list[dict[str, Any]] = [{"role": "user", "content": "hello"}]
        k1 = request_key("model-a", msgs, None, 0.0, 512)
        k2 = request_key("model-a", msgs, None, 0.0, 512)
        assert k1 == k2

    def test_different_model_different_key(self) -> None:
        msgs: list[dict[str, Any]] = [{"role": "user", "content": "hello"}]
        k1 = request_key("model-a", msgs, None, 0.0, 512)
        k2 = request_key("model-b", msgs, None, 0.0, 512)
        assert k1 != k2

    def test_different_messages_different_key(self) -> None:
        k1 = request_key("m", [{"role": "user", "content": "hi"}], None, 0.0, 512)
        k2 = request_key("m", [{"role": "user", "content": "hello"}], None, 0.0, 512)
        assert k1 != k2

    def test_different_temperature_different_key(self) -> None:
        msgs: list[dict[str, Any]] = [{"role": "user", "content": "q"}]
        k1 = request_key("m", msgs, None, 0.0, 512)
        k2 = request_key("m", msgs, None, 0.7, 512)
        assert k1 != k2

    def test_tools_none_vs_empty_list_same_key(self) -> None:
        msgs: list[dict[str, Any]] = [{"role": "user", "content": "q"}]
        k1 = request_key("m", msgs, None, 0.0, 512)
        k2 = request_key("m", msgs, [], 0.0, 512)
        assert k1 == k2

    def test_key_is_32_hex_chars(self) -> None:
        key = request_key("m", [], None, 0.0, 512)
        assert len(key) == 32
        assert all(c in "0123456789abcdef" for c in key)


class TestCassetteLibrary:
    def test_round_trip_save_lookup(self, tmp_path: Path) -> None:
        lib = CassetteLibrary(tmp_path)
        key = "abc123" * 5 + "ab"  # 32 chars
        p = _payload("Hello from cassette")
        lib.save(key, p)
        result = lib.lookup(key)
        assert result is not None
        assert result.content == "Hello from cassette"
        assert result.prompt_tokens == 10

    def test_lookup_miss_returns_none(self, tmp_path: Path) -> None:
        lib = CassetteLibrary(tmp_path)
        assert lib.lookup("no-such-key") is None

    def test_has_returns_false_for_missing(self, tmp_path: Path) -> None:
        lib = CassetteLibrary(tmp_path)
        assert lib.has("no-such-key") is False

    def test_has_returns_true_after_save(self, tmp_path: Path) -> None:
        lib = CassetteLibrary(tmp_path)
        key = "a" * 32
        lib.save(key, _payload())
        assert lib.has(key) is True

    def test_lookup_from_disk_after_cache_eviction(self, tmp_path: Path) -> None:
        lib1 = CassetteLibrary(tmp_path)
        key = "b" * 32
        lib1.save(key, _payload("disk payload"))

        lib2 = CassetteLibrary(tmp_path)  # fresh instance, empty cache
        result = lib2.lookup(key)
        assert result is not None
        assert result.content == "disk payload"

    def test_tool_calls_round_trip(self, tmp_path: Path) -> None:
        lib = CassetteLibrary(tmp_path)
        key = "c" * 32
        tc = ReplayToolCall(
            id="call_001",
            function=ReplayFunction(
                name="coverage_calculator",
                arguments='{"claim_amount": 1000.0}',
            ),
        )
        lib.save(key, _payload(tool_calls=[tc]))
        result = lib.lookup(key)
        assert result is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "call_001"
        assert result.tool_calls[0].function.name == "coverage_calculator"

    def test_creates_directory_on_init(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "sub" / "cassettes"
        assert not new_dir.exists()
        CassetteLibrary(new_dir)
        assert new_dir.is_dir()


class TestCassetteMissError:
    def test_is_key_error_subclass(self) -> None:
        err = CassetteMissError("missing key")
        assert isinstance(err, KeyError)

    def test_raised_on_explicit_call(self, tmp_path: Path) -> None:
        with pytest.raises(CassetteMissError):
            raise CassetteMissError("no cassette for this request")
