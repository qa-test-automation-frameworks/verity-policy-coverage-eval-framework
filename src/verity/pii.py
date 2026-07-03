"""Shared personal-data detection patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from verity.check_result import CheckResult


@dataclass(frozen=True)
class PiiPattern:
    pattern: re.Pattern[str]
    label: str
    replacement: str
    # Optional: only treat a match as PII when context_pattern also appears
    # within context_window characters immediately before it. Needed for
    # patterns (like a bare ISO date) that are structurally identical to
    # legitimate content the SUT is expected to state — a policy effective
    # date reads exactly like a date of birth — and can only be told apart
    # by nearby wording.
    context_pattern: re.Pattern[str] | None = None
    context_window: int = 0


_DOB_CONTEXT = re.compile(r"date of birth|\bdob\b|\bborn\b", re.IGNORECASE)

PII_PATTERNS: tuple[PiiPattern, ...] = (
    PiiPattern(
        pattern=re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
        label="date-of-birth",
        replacement="[DATE_REDACTED]",
        # Widest observed gap between the context phrase and the date itself
        # ("date of birth on file is 1985-03-22") is under 20 characters;
        # 40 leaves headroom without matching an unrelated date on the
        # other side of the sentence.
        context_pattern=_DOB_CONTEXT,
        context_window=40,
    ),
    PiiPattern(
        pattern=re.compile(r"\bMBR-\d{3,6}\b", re.IGNORECASE),
        label="member-id",
        replacement="[MEMBER_ID_REDACTED]",
    ),
    PiiPattern(
        pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        label="ssn-pattern",
        replacement="[SSN_REDACTED]",
    ),
    PiiPattern(
        pattern=re.compile(r"\b\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
        label="phone-pattern",
        replacement="[PHONE_REDACTED]",
    ),
)


def find_matches(text: str, pii_pattern: PiiPattern) -> list[re.Match[str]]:
    """Return every match of pii_pattern in text, applying its context gate if set.

    Matches without a satisfied context_pattern (when one is configured) are
    dropped rather than treated as PII, so a pattern like the bare-ISO-date
    detector above only fires near actual birth-date wording.
    """
    matches = list(pii_pattern.pattern.finditer(text))
    if pii_pattern.context_pattern is None:
        return matches
    gated: list[re.Match[str]] = []
    for m in matches:
        window_start = max(0, m.start() - pii_pattern.context_window)
        window = text[window_start : m.end()]
        if pii_pattern.context_pattern.search(window):
            gated.append(m)
    return gated


def scan_pii(text: str, member_name: str = "") -> list[str]:
    """Return a list of PII tokens found in text.

    Checks for date-of-birth patterns, member IDs, SSN-like patterns, and
    phone numbers. Optionally checks for a specific member name.
    """
    found: list[str] = []
    for pii_pattern in PII_PATTERNS:
        matches = find_matches(text, pii_pattern)
        if matches:
            found.append(f"{pii_pattern.label}:{matches[0].group()}")
    if member_name and member_name.strip() and member_name.lower() in text.lower():
        found.append(f"name:{member_name}")
    return found


def check_pii(response: Any, member_name: str = "") -> CheckResult:
    """Verify that no PII appears in the response answer text.

    Defect #8 manifests when member.name or member.dob is echoed in the
    response text despite the output scrubber in guardrails.py.
    """
    answer = str(getattr(response, "answer", ""))
    pii_found = scan_pii(answer, member_name=member_name)
    if pii_found:
        return CheckResult(False, f"PII found in response answer: {pii_found}")
    return CheckResult(True)


def scan_log_pii(messages: list[str], member_name: str = "") -> list[str]:
    """Return PII tokens found across captured log messages."""
    combined = "\n".join(messages)
    return scan_pii(combined, member_name=member_name)
