"""Tests for durable diagnostics from live semantic evaluations."""

from __future__ import annotations

import json
from pathlib import Path

from verity.semantic_reporting import append_failure_event, failure_reason, redact_failure_text


def test_failure_reason_prefers_assertion_or_exception_line() -> None:
    trace = "traceback\n  File test.py\nE   AssertionError: score below threshold"
    assert failure_reason(trace) == ("AssertionError: score below threshold")


def test_failure_text_redacts_common_secret_shapes(monkeypatch) -> None:
    monkeypatch.setenv("VERITY_GOOGLE_API_KEY", "my-test-key")
    text = "api_key=my-test-key Authorization: Bearer abc123 sk-abcdefghijklmnop"
    redacted = redact_failure_text(text)
    assert "my-test-key" not in redacted
    assert "abc123" not in redacted
    assert "sk-abcdefghijklmnop" not in redacted
    assert "[REDACTED]" in redacted


def test_append_failure_event_flushes_jsonl_with_reason_and_details(tmp_path: Path) -> None:
    path = tmp_path / "reports" / "semantic" / "failures.jsonl"
    event = append_failure_event(
        path,
        nodeid="tests/semantic/test_eval.py::test_case",
        longrepr="Traceback\nE   RuntimeError: provider returned 503 ServiceUnavailable",
    )

    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == event
    assert saved["nodeid"] == "tests/semantic/test_eval.py::test_case"
    assert saved["reason"] == "RuntimeError: provider returned 503 ServiceUnavailable"
    assert saved["outcome"] == "failed"
    assert saved["timestamp"].endswith("Z")
