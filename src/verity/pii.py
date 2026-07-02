"""Shared personal-data detection patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass


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
