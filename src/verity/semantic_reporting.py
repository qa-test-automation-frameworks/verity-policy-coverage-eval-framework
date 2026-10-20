"""Durable, redacted failure diagnostics for live semantic evaluations."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|authorization|secret)\s*[:=]\s*([^\s,;]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_TOKEN_SHAPE = re.compile(r"\b(?:sk|nvapi|AIza)[-_][A-Za-z0-9_-]{12,}\b")
_MAX_DETAIL_CHARS = 12_000


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
