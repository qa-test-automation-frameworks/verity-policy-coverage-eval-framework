"""Deterministic temporal checks for explicitly versioned golden expectations.

This module handles only the narrow, authored USD amount contract in a golden
case. It is not a general-purpose temporal or natural-language resolver.
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict

from verity.golden import TemporalAmountExpectation

_CURRENCY_AMOUNT = re.compile(
    r"(?<![\w])(?:(?:USD)\s*\$?|\$)\s*(\d{1,3}(?:,\d{3})*|\d+)"
    r"(?:\.(\d{1,2}))?(?!\d|,(?=\d)|\.(?=\d))",
    re.IGNORECASE,
)
_VALUE_ONLY = re.compile(r"\s*(?:(?:USD)\s*\$?|\$)?\s*(\d+(?:\.\d{1,2})?)\s*[.!]?\s*", re.I)
_CLAUSE_BOUNDARY = re.compile(
    r"(?<=[!?])\s+|;\s*|\n+|\.(?!\d)\s+|\b(?:but|however|although|whereas)\b", re.I
)
_CURRENT_CUE = re.compile(r"\b(?:current|currently|now|amended|effective)\b", re.I)
_HISTORICAL_CUE = re.compile(
    r"\b(?:old|original|previous|previously|prior|formerly|historical|superseded|"
    r"supersede|superseding|replaced|before)\b",
    re.I,
)
_FROM_AMOUNT = re.compile(r"\bfrom\s*$", re.I)


class TemporalCheckResult(TypedDict):
    status: Literal["PASS", "FAIL", "REVIEW"]
    current_claim: int | None
    authoritative_evidence_id: str
    reasons: list[str]


def _minor_units(whole: str, fraction: str | None) -> int:
    cents = (fraction or "").ljust(2, "0")
    return int(whole.replace(",", "")) * 100 + int(cents or "0")


def _split_clauses(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for boundary in _CLAUSE_BOUNDARY.finditer(text):
        if boundary.start() > start:
            spans.append((start, boundary.start()))
        start = boundary.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _value_only_amount(answer: str) -> int | None:
    match = _VALUE_ONLY.fullmatch(answer)
    if match is None:
        return None
    whole, dot, fraction = match.group(1).partition(".")
    return _minor_units(whole, fraction if dot else None)


def _format_usd(amount_minor: int) -> str:
    return f"${amount_minor // 100:,}.{amount_minor % 100:02d}"


def _distance(cue_start: int, cue_end: int, amount_start: int, amount_end: int) -> int:
    if cue_end <= amount_start:
        return amount_start - cue_end
    if amount_end <= cue_start:
        return cue_start - amount_end
    return 0


def _assigned_cue_distances(
    clause: str, matches: list[re.Match[str]], pattern: re.Pattern[str]
) -> list[list[int]]:
    assigned: list[list[int]] = [[] for _ in matches]
    for cue in pattern.finditer(clause):
        distances = [
            _distance(cue.start(), cue.end(), match.start(), match.end()) for match in matches
        ]
        nearest = min(distances)
        if nearest <= 64:
            for index, distance in enumerate(distances):
                if distance == nearest:
                    assigned[index].append(distance)
    return assigned


def _result(
    expectation: TemporalAmountExpectation,
    status: Literal["PASS", "FAIL", "REVIEW"],
    current_claim: int | None,
    reason: str,
) -> TemporalCheckResult:
    return {
        "status": status,
        "current_claim": current_claim,
        "authoritative_evidence_id": expectation.authoritative_evidence_id,
        "reasons": [reason],
    }


def check_temporal_amount(
    expectation: TemporalAmountExpectation, answer: object
) -> TemporalCheckResult:
    """Check whether a bounded answer states the expected current USD amount.

    A currency amount must be near an explicit current cue or an explicit
    historical cue. Unsupported structure and ambiguous wording return REVIEW.
    An explicitly current superseded amount returns FAIL even when the answer
    also mentions the correct amount elsewhere.
    """
    if not isinstance(answer, str) or not answer.strip():
        return _result(expectation, "REVIEW", None, "No answer text is available to inspect.")

    value_only = _value_only_amount(answer)
    occurrences = [(value_only, True, False)] if value_only is not None else []
    spans = _split_clauses(answer)
    for start, end in spans if value_only is None else []:
        clause = answer[start:end]
        matches = list(_CURRENCY_AMOUNT.finditer(clause))
        if not matches:
            continue
        assigned_current = _assigned_cue_distances(clause, matches, _CURRENT_CUE)
        assigned_historical = _assigned_cue_distances(clause, matches, _HISTORICAL_CUE)
        for index, match in enumerate(matches):
            prefix = clause[: match.start()]
            if _FROM_AMOUNT.search(prefix):
                assigned_historical[index].append(0)
            current_distance = min(assigned_current[index], default=None)
            historical_distance = min(assigned_historical[index], default=None)
            current = current_distance is not None and (
                historical_distance is None or current_distance < historical_distance
            )
            historical = historical_distance is not None and (
                current_distance is None or historical_distance < current_distance
            )
            if current_distance == historical_distance and current_distance is not None:
                current = historical = True
            amount = _minor_units(match.group(1), match.group(2))
            occurrences.append((amount, current, historical))

    if not occurrences:
        return _result(
            expectation,
            "REVIEW",
            None,
            "No supported USD amount or value-only amount was found.",
        )

    current_amounts: list[int] = []
    unclear_amount = False
    for amount, current, historical in occurrences:
        if current and historical:
            unclear_amount = True
        elif current:
            current_amounts.append(amount)
        elif not historical:
            unclear_amount = True

    stale_claims = [
        amount for amount in current_amounts if amount in expectation.superseded_amounts_minor
    ]
    if stale_claims:
        stale = stale_claims[-1]
        return _result(
            expectation,
            "FAIL",
            stale,
            f"The answer explicitly claims superseded amount {_format_usd(stale)} is current.",
        )

    unique_current = set(current_amounts)
    if unclear_amount:
        return _result(
            expectation,
            "REVIEW",
            None,
            "An amount is not clearly labeled current or historical.",
        )
    if len(unique_current) > 1:
        return _result(
            expectation,
            "REVIEW",
            None,
            "Conflicting current-value clauses contain different amounts.",
        )
    if not unique_current:
        return _result(
            expectation,
            "REVIEW",
            None,
            "No unambiguous current-value claim was found.",
        )

    current_claim = next(iter(unique_current))
    if current_claim == expectation.current_amount_minor:
        return _result(
            expectation,
            "PASS",
            current_claim,
            f"The current-value claim matches {_format_usd(expectation.current_amount_minor)}.",
        )
    return _result(
        expectation,
        "REVIEW",
        current_claim,
        f"The current-value claim {_format_usd(current_claim)} is not in the authored expectation.",
    )
