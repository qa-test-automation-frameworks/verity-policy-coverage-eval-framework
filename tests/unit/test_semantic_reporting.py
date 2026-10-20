"""Tests for durable diagnostics from live semantic evaluations."""

from __future__ import annotations

import json
from pathlib import Path

from verity.semantic_reporting import (
    append_failure_event,
    failure_reason,
    faithfulness_sut_failure_message,
    redact_failure_text,
    semantic_sut_failure_message,
)


def test_failure_reason_prefers_assertion_or_exception_line() -> None:
    trace = "traceback\n  File test.py\nE   AssertionError: score below threshold"
    assert failure_reason(trace) == ("AssertionError: score below threshold")


def test_faithfulness_failure_message_ignores_empty_success_category() -> None:
    assert faithfulness_sut_failure_message("control-case", "") is None


def test_faithfulness_failure_message_preserves_real_failure_category() -> None:
    assert faithfulness_sut_failure_message("control-case", "provider_unavailable") == (
        "System-under-test request failed (provider_unavailable); "
        "faithfulness score is unavailable for 'control-case'."
    )


def test_semantic_failure_message_reports_sut_failure_before_scoring() -> None:
    assert semantic_sut_failure_message("case-1", "empty_final_answer", "safe fallback") == (
        "System-under-test request failed (empty_final_answer); "
        "semantic score is unavailable for 'case-1'."
    )


def test_semantic_failure_message_rejects_empty_success_response() -> None:
    assert semantic_sut_failure_message("case-1", "", "  \n") == (
        "System-under-test returned an empty answer; semantic score is unavailable for 'case-1'."
    )


def test_semantic_failure_message_accepts_successful_response() -> None:
    assert semantic_sut_failure_message("case-1", "", "Coverage details") is None


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
