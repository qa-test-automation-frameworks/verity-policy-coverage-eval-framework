"""Shared personal-data detection patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PiiPattern:
    pattern: re.Pattern[str]
    label: str
    replacement: str


PII_PATTERNS: tuple[PiiPattern, ...] = (
    PiiPattern(
        pattern=re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
        label="date-of-birth",
        replacement="[DATE_REDACTED]",
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
