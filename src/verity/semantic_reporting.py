"""Durable, redacted failure diagnostics for live semantic evaluations."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)([\"']?(?:api[_-]?key|access[_-]?token|authorization|secret)[\"']?)"
    r"\s*[:=]\s*[\"']?([^\s,;\"'}]+)[\"']?"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_TOKEN_SHAPE = re.compile(
    r"\b(?:sk-(?:or-v1-)?|sk_|nvapi-|AIza|gsk_|xai-|gh[pousr]_)[A-Za-z0-9_-]{12,}\b"
)
_MAX_DETAIL_CHARS = 12_000


def faithfulness_sut_failure_message(case_id: str, failure_category: str | None) -> str | None:
    """Describe an actual SUT failure; an empty category means the response succeeded."""
    if not failure_category:
        return None
    return (
        f"System-under-test request failed ({failure_category}); "
        f"faithfulness score is unavailable for {case_id!r}."
    )


def semantic_sut_failure_message(
    case_id: str, failure_category: str | None, answer: str
) -> str | None:
    """Describe an SUT failure before passing its response to a semantic judge."""
    if failure_category:
        return (
            f"System-under-test request failed ({failure_category}); "
            f"semantic score is unavailable for {case_id!r}."
        )
    if not answer.strip():
        return (
            "System-under-test returned an empty answer; "
            f"semantic score is unavailable for {case_id!r}."
        )
    return None


def redact_failure_text(value: str) -> str:
    """Redact common credential forms and configured API-key values."""
    redacted = value
    for name, secret in os.environ.items():
        if secret and any(part in name.upper() for part in ("API_KEY", "TOKEN", "SECRET")):
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = _BEARER.sub("Bearer [REDACTED]", redacted)
    redacted = _SECRET_ASSIGNMENT.sub(r"\1=[REDACTED]", redacted)
    return _TOKEN_SHAPE.sub("[REDACTED_TOKEN]", redacted)


def failure_reason(longrepr: str) -> str:
    """Return a compact assertion/exception cause suitable for live console output."""
    lines = [line.strip() for line in longrepr.splitlines() if line.strip()]
    candidates = [line[2:].strip() for line in lines if line.startswith("E ")]
    fallback = lines[-1] if lines else "No failure detail available"
    reason = candidates[-1] if candidates else fallback
    return redact_failure_text(reason)[:500]


def append_failure_event(path: Path, *, nodeid: str, longrepr: str) -> dict[str, Any]:
    """Append and flush one failure event so cancellation preserves earlier failures."""
    details = redact_failure_text(longrepr)[-_MAX_DETAIL_CHARS:]
    event: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "nodeid": nodeid,
        "outcome": "failed",
        "reason": failure_reason(longrepr),
        "details": details,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return event


def _redact_evidence_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_failure_text(value)
    if isinstance(value, list):
        return [_redact_evidence_value(item) for item in value]
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).upper()
            if any(
                part in normalized_key
                for part in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "AUTH", "CREDENTIAL")
            ):
                safe[str(key)] = "[REDACTED]"
            else:
                safe[str(key)] = _redact_evidence_value(item)
        return safe
    return value


def append_case_evidence_event(path: Path, *, event: dict[str, Any]) -> dict[str, Any]:
    """Append one semantic case trace, redacting credentials before persistence.

    These verbose-only diagnostics may include model-generated answer text and
    synthetic evaluation inputs. Keep them in the short-retention run artifact,
    not the durable trend or portfolio evidence records.
    """
    safe_event = cast(dict[str, Any], _redact_evidence_value(event))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(safe_event, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return safe_event
