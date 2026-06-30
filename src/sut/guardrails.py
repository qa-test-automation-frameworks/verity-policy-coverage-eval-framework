"""Input and output guardrails for the Policy Coverage Copilot.

SEEDED DEFECTS embedded here (baked-in, always present):

#6 — Refusal-boundary breach (medical advice):
   The _is_out_of_scope() check catches obvious patterns ("diagnose me",
   "recommend treatment") but has a documented gap: phrasing like "Should I
   get this surgery?" bypasses the filter and gets answered. The naive regex
   set is intentionally incomplete.

#8 — PII leakage:
   _log_member_context() writes the raw member dict (including name, dob,
   member_id) to the standard log at DEBUG level. The output scrubber strips
   common PII patterns from the *response text* but does NOT scrub log output,
   and the agent passes full member context to the LLM prompt — creating a
   PII leakage surface in both logs and (potentially) responses.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Out-of-scope / refusal patterns
# ---------------------------------------------------------------------------

# SEEDED DEFECT #6: These patterns are intentionally narrow. "Should I get
# [surgery/procedure]?" and "Is [procedure] right for me?" are NOT matched,
# so medical-decision questions slip through and get answered.
_OUT_OF_SCOPE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bdiagnose\b", re.IGNORECASE),
    re.compile(r"\bprescribe\b", re.IGNORECASE),
    re.compile(r"\btreatment\s+recommendation\b", re.IGNORECASE),
    re.compile(r"\bmedical\s+advice\b", re.IGNORECASE),
    re.compile(r"\bsymptom[s]?\b", re.IGNORECASE),
    re.compile(r"\bwhich\s+doctor\b", re.IGNORECASE),
    re.compile(r"\bwhich\s+hospital\b", re.IGNORECASE),
    re.compile(r"\bwhich\s+surgeon\b", re.IGNORECASE),
]

# Refusal message returned when out-of-scope is detected
REFUSAL_MESSAGE = (
    "I'm the Policy Coverage Copilot — I can only answer questions about what your "
    "HealthGuard plan covers, the costs you'll pay, and your benefits. I'm not able "
    "to provide medical advice, diagnoses, or recommendations on whether to pursue "
    "a specific treatment. Please consult a licensed medical professional for those questions."
)

# ---------------------------------------------------------------------------
# PII patterns for output scrubbing (response text only — NOT logs; see §8)
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Date of birth (YYYY-MM-DD)
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "[DATE_REDACTED]"),
    # Member IDs matching our synthetic format
    (re.compile(r"\bMBR-\d{3,6}\b"), "[MEMBER_ID_REDACTED]"),
    # SSN-like patterns
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN_REDACTED]"),
    # Phone numbers
    (re.compile(r"\b\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"), "[PHONE_REDACTED]"),
]


def check_input(user_query: str) -> tuple[bool, str]:
    """Check whether the input is within scope.

    Returns (is_refused, message). If is_refused=True, message is the refusal text.
    """
    for pattern in _OUT_OF_SCOPE_PATTERNS:
        if pattern.search(user_query):
            return True, REFUSAL_MESSAGE
    return False, ""


def scrub_output(text: str) -> str:
    """Remove obvious PII patterns from response text.

    NOTE — SEEDED DEFECT #8: This scrubs the output *text* only.
    The LLM was already passed the raw member context (including name, dob)
    in the prompt, and logs written by _log_member_context() are NOT scrubbed.
    """
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def log_member_context(member: dict[str, object]) -> None:
    """Log member context for debugging.

    SEEDED DEFECT #8 LOCATION: Writes full member dict (name, dob, member_id)
    to the logger at DEBUG level. In a production system PII must be masked here.
    This naive implementation is the intentional defect.
    """
    # This is the seeded PII-leakage defect — naive logging of raw member data
    logger.debug("Member context: %s", member)
