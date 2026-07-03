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


def _parse_citation(raw: str) -> tuple[str, str]:
    """Split a "source: section" citation string into (source, section).

    section is "" when raw has no ":" (a bare source, e.g. an expected_citations
    entry that only names the file).
    """
    source, _, section = raw.partition(":")
    return source.strip(), section.strip()


def check_citations(
    case: Any,
    response: Any,
    retrieved_sources: list[str] | None = None,
    retrieved_chunks: list[Any] | None = None,
) -> CheckResult:
    """Verify cited sources are grounded in retrieved context and match expectations.

    - Each citation must reference a source that was actually retrieved
      (`retrieved_sources`, source-file-level).
    - When `retrieved_chunks` is given (objects with `.source`/`.section`, e.g.
      `sut.retriever.Chunk`), each citation's exact (source, section) pair must
      match a retrieved chunk — catches a citation that names a source file that
      was retrieved but a section within it that was not (source-level checking
      alone can't tell "right file, wrong section" from a real hit).
    - If case.expected_citations is non-empty, every expected entry must appear.
      An entry may be a bare source ("gold.md") or section-qualified
      ("gold.md: §2.1"); a section-qualified entry requires an exact
      (source, section) match in the response's own citations.
    """
    citations: list[str] = list(getattr(response, "citations", []))
    parsed_citations = [_parse_citation(c) for c in citations]
    cited_sources = {source for source, _ in parsed_citations}
    cited_pairs = {(source, section) for source, section in parsed_citations if section}

    if retrieved_sources is not None:
        retrieved_set = set(retrieved_sources)
        unsupported = cited_sources - retrieved_set
        if unsupported:
            return CheckResult(
                False,
                f"Citations reference sources not in retrieved context: {sorted(unsupported)}",
            )

    if retrieved_chunks is not None:
        retrieved_pairs = {
            (getattr(chunk, "source", ""), getattr(chunk, "section", ""))
            for chunk in retrieved_chunks
        }
        mismatched = sorted(
            f"{source}: {section}"
            for source, section in cited_pairs
            if (source, section) not in retrieved_pairs
        )
        if mismatched:
            return CheckResult(
                False,
                "Citations reference a section not present in the retrieved context "
                f"(right file, wrong section, or fabricated section): {mismatched}",
            )

    if case.expected_citations:
        missing: list[str] = []
        for entry in case.expected_citations:
            source, section = _parse_citation(entry)
            if section:
                if (source, section) not in cited_pairs:
                    missing.append(entry)
            elif source not in cited_sources:
                missing.append(entry)
        if missing:
            return CheckResult(
                False,
                f"Expected citation(s) missing from response: {sorted(missing)}",
            )

    return CheckResult(True)


def check_claim_numbers_grounded(response: Any, retrieved_chunks: list[Any]) -> CheckResult:
    """Verify every number the answer states also appears in some retrieved chunk's text.

    check_citations only proves the *source file* was retrieved; it says nothing about
    whether the specific amount cited actually appears in that (or any) retrieved chunk.
    A model can cite the right document while stating a number found nowhere in the
    retrieved context — a claim/citation-level groundedness gap, not a source-level one.

    Not meaningful for cases whose answer is a computed value (e.g. coverage_calculator
    output) rather than a direct lookup — callers should skip those (typically:
    case.expected_tool is set).
    """
    answer = str(getattr(response, "answer", ""))
    claimed_numbers = extract_numbers(answer)
    if not claimed_numbers:
        return CheckResult(True, "No numeric claims to ground")

    chunk_numbers: set[float] = set()
    for chunk in retrieved_chunks:
        chunk_numbers.update(extract_numbers(str(getattr(chunk, "text", ""))))

    ungrounded = [n for n in claimed_numbers if not any(abs(n - cn) < 1e-6 for cn in chunk_numbers)]
    if ungrounded:
        return CheckResult(
            False,
            f"Answer states number(s) not found in any retrieved chunk: {ungrounded}",
        )
    return CheckResult(True)


# A leading '-' only counts as a negative sign when it is not itself preceded
# by a letter/digit, so "Tier-1" (a section label, not "negative one") is not
# misread as -1 while "-$50" and " -50" still are.
_DOLLAR_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])-?\$?\s*\d[\d,]*(?:\.\d+)?%?")

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def extract_numbers(text: str) -> list[float]:
    """Extract every number in the text as a float, dollar signs/commas stripped.

    A "%" match is also emitted as a fraction (e.g. "20%" -> 20.0 and 0.20) so a
    numeric_expectation authored against the domain's fraction convention
    (coinsurance_member: 0.20, matching CoverageInput) still matches text that
    states the same value as a percentage.

    An ISO date (e.g. "2024-07-01") is excluded entirely rather than left to
    fall through to _DOLLAR_NUMBER_RE: the month/day segments read as bare
    digits ("07", "01") and would otherwise surface as spurious 7.0/1.0
    claims unrelated to any dollar amount or percentage in the text. Dates
    are extracted separately by text_expectations._extract_dates.
    """
    date_spans = [m.span() for m in _ISO_DATE_RE.finditer(text)]

    def _within_a_date(start: int, end: int) -> bool:
        return any(d_start <= start and end <= d_end for d_start, d_end in date_spans)

    numbers: list[float] = []
    for match in _DOLLAR_NUMBER_RE.finditer(text):
        if _within_a_date(*match.span()):
            continue
        raw = match.group()
        is_percent = raw.endswith("%")
        cleaned = raw.replace("$", "").replace(",", "").replace("%", "").strip()
        if not cleaned or cleaned == "-":
            continue
        try:
            value = float(cleaned)
        except ValueError:
            continue
        numbers.append(value)
        if is_percent:
            numbers.append(value / 100)
    return numbers


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
