"""Literal-token and typed numeric/date expectation checks against an answer.

must_contain/must_not_contain are literal substring checks: a case that
expects "$3,800" fails if the model correctly states "3800.00" or "three
thousand eight hundred dollars". Numeric/date expectations compare parsed
values instead, so a differently-formatted-but-correct answer still passes,
and a case can express "must state an amount >= X" rather than only
"must contain the exact string X".
"""

from __future__ import annotations

import re
from typing import Any

from verity.check_result import CheckResult
from verity.claim_grounding import extract_numbers
from verity.golden import DateExpectation, GoldenCase, NumericExpectation

_THOUSANDS_SEP_RE = re.compile(r"(?<=\d),(?=\d{3}(?:\D|$))")


def _normalize_numerics(text: str) -> str:
    """Strip thousands-separator commas from digit runs (e.g. '1,660' -> '1660')
    so a must_contain/must_not_contain token matches regardless of comma formatting."""
    return _THOUSANDS_SEP_RE.sub("", text)


def check_must_contain(case: GoldenCase, response: Any) -> CheckResult:
    """Verify all must_contain tokens appear (case-insensitive) in the answer."""
    answer = _normalize_numerics(str(getattr(response, "answer", "")).lower())
    missing = [
        token for token in case.must_contain if _normalize_numerics(token.lower()) not in answer
    ]
    if missing:
        return CheckResult(False, f"Answer missing required tokens: {missing}")
    return CheckResult(True)


def check_must_contain_any(case: GoldenCase, response: Any) -> CheckResult:
    """Verify each must_contain_any group has at least one alternate phrasing
    present (case-insensitive) in the answer."""
    answer = _normalize_numerics(str(getattr(response, "answer", "")).lower())
    unsatisfied = [
        group
        for group in case.must_contain_any
        if not any(_normalize_numerics(phrase.lower()) in answer for phrase in group)
    ]
    if unsatisfied:
        return CheckResult(False, f"Answer missing all alternate phrasings for: {unsatisfied}")
    return CheckResult(True)


def check_must_not_contain(case: GoldenCase, response: Any) -> CheckResult:
    """Verify none of the must_not_contain tokens appear (case-insensitive) in the answer."""
    answer = _normalize_numerics(str(getattr(response, "answer", "")).lower())
    found = [
        token for token in case.must_not_contain if _normalize_numerics(token.lower()) in answer
    ]
    if found:
        return CheckResult(False, f"Answer contains forbidden tokens: {found}")
    return CheckResult(True)


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
_MONTH_DAY_YEAR_RE = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE
)
_MONTH_DAY_RE = re.compile(r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})\b", re.IGNORECASE)


def _numeric_matches(numbers: list[float], expectation: NumericExpectation) -> bool:
    if expectation.comparator == "range":
        assert expectation.min_value is not None and expectation.max_value is not None
        return any(expectation.min_value <= n <= expectation.max_value for n in numbers)
    assert expectation.value is not None
    v = expectation.value
    if expectation.comparator == "eq":
        return any(abs(n - v) <= expectation.tolerance for n in numbers)
    if expectation.comparator == "gte":
        return any(n >= v for n in numbers)
    if expectation.comparator == "lte":
        return any(n <= v for n in numbers)
    if expectation.comparator == "gt":
        return any(n > v for n in numbers)
    if expectation.comparator == "lt":
        return any(n < v for n in numbers)
    return False


def check_numeric_expectations(case: GoldenCase, response: Any) -> CheckResult:
    """Verify each numeric_expectations entry is satisfied by some number in the answer."""
    answer = str(getattr(response, "answer", ""))
    numbers = extract_numbers(answer)
    failures = [
        exp.description for exp in case.numeric_expectations if not _numeric_matches(numbers, exp)
    ]
    if failures:
        return CheckResult(
            False, f"Numeric expectation(s) not satisfied: {failures} (found numbers: {numbers})"
        )
    return CheckResult(True)


def _extract_dates(text: str) -> list[str]:
    """Extract every date mention in the text, normalized to ISO YYYY-MM-DD.

    Month-only-and-day mentions (no year, e.g. "January 1") are resolved
    against every year appearing elsewhere in the text as an ISO or
    month-day-year date, so a plan-year-reset answer naming "January 1"
    alongside "2024-07-01" still matches a year-scoped expectation.
    """
    dates: set[str] = set()
    years_in_text: set[int] = set()

    for y, m, d in _ISO_DATE_RE.findall(text):
        dates.add(f"{y}-{m}-{d}")
        years_in_text.add(int(y))

    for month_name, day, year in _MONTH_DAY_YEAR_RE.findall(text):
        month = _MONTHS[month_name.lower()]
        dates.add(f"{year}-{month:02d}-{int(day):02d}")
        years_in_text.add(int(year))

    month_day_only = _MONTH_DAY_RE.findall(text)
    if month_day_only and years_in_text:
        for month_name, day in month_day_only:
            month = _MONTHS[month_name.lower()]
            for year in years_in_text:
                dates.add(f"{year}-{month:02d}-{int(day):02d}")

    return sorted(dates)


def _date_matches(dates: list[str], expectation: DateExpectation) -> bool:
    for d in dates:
        if expectation.on_or_after is not None and d < expectation.on_or_after:
            continue
        if expectation.on_or_before is not None and d > expectation.on_or_before:
            continue
        return True
    return False


def check_date_expectations(case: GoldenCase, response: Any) -> CheckResult:
    """Verify each date_expectations entry is satisfied by some date in the answer."""
    answer = str(getattr(response, "answer", ""))
    dates = _extract_dates(answer)
    failures = [exp.description for exp in case.date_expectations if not _date_matches(dates, exp)]
    if failures:
        return CheckResult(
            False, f"Date expectation(s) not satisfied: {failures} (found dates: {dates})"
        )
    return CheckResult(True)
