"""Reusable deterministic checks for the evaluation suite.

Each check takes a GoldenCase (expectations) and a response object (actual
SUT output) and returns a CheckResult. Checks are intentionally pure functions
with no side effects, so they compose freely and are trivially unit-testable.

Import note: response parameters are typed as Any to avoid a circular package
dependency (verity -> sut -> verity). Tool-specific argument schemas are registered
by target packages through register_tool_arg_validator(), so framework checks do not
import the demo target. All attribute access is explicit and guarded so type errors
surface as CheckResult failures, not exceptions.

The individual check families live in focused modules (response_schema,
escalation, tool_args, pii, injection_guard, claim_grounding,
text_expectations) and are re-exported here so existing
`from verity.checks import X` call sites keep working unchanged.
"""

from __future__ import annotations

from verity.check_result import CheckResult
from verity.claim_grounding import (
    check_citations,
    check_claim_numbers_grounded,
    check_policy_claims_grounded,
    extract_numbers,
)
from verity.escalation import check_human_review, check_refusal
from verity.injection_guard import (
    check_injection,
    check_no_adjudication_language,
    check_prompt_leakage,
    scan_injection,
    scan_prompt_leakage,
)
from verity.pii import check_pii, scan_log_pii, scan_pii
from verity.response_schema import AnswerEvidence, validate_response_schema
from verity.text_expectations import (
    _extract_dates,
    check_date_expectations,
    check_must_contain,
    check_must_contain_any,
    check_must_not_contain,
    check_numeric_expectations,
)
from verity.tool_args import (
    ToolArgValidator,
    check_tool_args,
    register_tool_arg_validator,
)

__all__ = [
    "AnswerEvidence",
    "CheckResult",
    "ToolArgValidator",
    "_extract_dates",
    "check_citations",
    "check_claim_numbers_grounded",
    "check_date_expectations",
    "check_human_review",
    "check_injection",
    "check_must_contain",
    "check_must_contain_any",
    "check_must_not_contain",
    "check_no_adjudication_language",
    "check_numeric_expectations",
    "check_pii",
    "check_policy_claims_grounded",
    "check_prompt_leakage",
    "check_refusal",
    "check_tool_args",
    "extract_numbers",
    "register_tool_arg_validator",
    "scan_injection",
    "scan_log_pii",
    "scan_pii",
    "scan_prompt_leakage",
    "validate_response_schema",
]
