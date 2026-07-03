"""Deterministic support checks for qualitative policy statements."""

from __future__ import annotations

import re
from typing import Any

from verity.check_result import CheckResult

_POLICY_CLAIM_TERMS = frozenset(
    {
        "authorization",
        "coinsurance",
        "copay",
        "covered",
        "coverage",
        "covers",
        "deductible",
        "effective",
        "eligible",
        "excluded",
        "exclusion",
        "expires",
        "human review",
        "limit",
        "limits",
        "network",
        "not covered",
        "prior",
        "required",
        "requires",
        "rider",
        "waiting",
    }
)

_CLAIM_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "and",
        "any",
        "are",
        "because",
        "been",
        "but",
        "can",
        "cannot",
        "could",
        "does",
        "for",
        "from",
        "have",
        "into",
        "may",
        "not",
        "per",
        "plan",
        "policy",
        "should",
        "that",
        "the",
        "this",
        "under",
        "with",
        "your",
    }
)

_GENERIC_CLAIM_TERMS = frozenset(
    {
        "covered",
        "coverage",
        "covers",
        "excluded",
        "exclusion",
        "plan",
        "policy",
        "service",
        "services",
    }
)


def check_policy_claims_grounded(response: Any, retrieved_chunks: list[Any]) -> CheckResult:
    """Verify qualitative policy claims have lexical support in retrieved text."""
    answer = str(getattr(response, "answer", ""))
    claims = _extract_policy_claims(answer)
    if not claims:
        return CheckResult(True, "No material policy claims to ground")

    chunk_texts = [str(getattr(chunk, "text", "")) for chunk in retrieved_chunks]
    if not chunk_texts:
        return CheckResult(False, f"Policy claim(s) have no retrieved support: {claims}")

    unsupported = [
        claim for claim in claims if not _claim_supported_by_any_chunk(claim, chunk_texts)
    ]
    if unsupported:
        return CheckResult(
            False,
            f"Policy claim(s) not supported by retrieved chunks: {unsupported}",
        )
    return CheckResult(True)


def _extract_policy_claims(answer: str) -> list[str]:
    claims: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", answer.strip()):
        normalized = _normalize_claim_text(sentence)
        if normalized and any(term in normalized for term in _POLICY_CLAIM_TERMS):
            claims.append(sentence.strip())
    return claims


def _claim_supported_by_any_chunk(claim: str, chunk_texts: list[str]) -> bool:
    claim_terms = _significant_claim_terms(claim)
    if not claim_terms:
        return True
    return any(
        _coverage_polarity_compatible(claim, chunk_text)
        and _has_enough_claim_overlap(claim_terms, _significant_claim_terms(chunk_text))
        for chunk_text in chunk_texts
    )


def _has_enough_claim_overlap(claim_terms: set[str], chunk_terms: set[str]) -> bool:
    overlap = claim_terms & chunk_terms
    return len(overlap) >= 2 or bool(overlap - _GENERIC_CLAIM_TERMS)


def _coverage_polarity_compatible(claim: str, chunk_text: str) -> bool:
    normalized_claim = _normalize_claim_text(claim)
    normalized_chunk = _normalize_claim_text(chunk_text)
    claim_says_covered = _has_positive_coverage_term(normalized_claim)
    claim_says_excluded = _has_negative_coverage_term(normalized_claim)
    chunk_says_covered = _has_positive_coverage_term(normalized_chunk)
    chunk_says_excluded = _has_negative_coverage_term(normalized_chunk)
    if claim_says_covered and chunk_says_excluded and not chunk_says_covered:
        return False
    return not (claim_says_excluded and chunk_says_covered and not chunk_says_excluded)


def _has_positive_coverage_term(text: str) -> bool:
    return bool(re.search(r"\b(?:covers|coverage|covered)\b", text)) and "not covered" not in text


def _has_negative_coverage_term(text: str) -> bool:
    return bool(re.search(r"\b(?:exclude|excludes|excluded|excluding|exclusion)\b", text)) or (
        "not covered" in text
    )


def _significant_claim_terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9-]{2,}", _normalize_claim_text(text))
        if token not in _CLAIM_STOPWORDS
    }


def _normalize_claim_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()
