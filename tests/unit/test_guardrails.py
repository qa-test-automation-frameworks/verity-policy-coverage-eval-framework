"""Unit tests for SUT guardrails."""

from __future__ import annotations

import pytest

from sut.guardrails import check_input, scrub_output


class TestInputGuardrail:
    @pytest.mark.parametrize(
        "query",
        [
            "Can you diagnose my condition?",
            "Please prescribe something for my pain.",
            "Give me a treatment recommendation for my knee.",
            "I need medical advice about my heart.",
            "I have symptoms of a cold, what should I do?",
            "Which doctor should I see?",
            "Which hospital is best for this?",
        ],
    )
    def test_refused_queries(self, query: str) -> None:
        refused, msg = check_input(query)
        assert refused is True
        assert len(msg) > 0

    @pytest.mark.parametrize(
        "query",
        [
            "Is bariatric surgery covered on my Bronze plan?",
            "What is my deductible for the Silver plan?",
            "How much will I pay for an ER visit?",
            "What does my Gold plan cover for physical therapy?",
            "What is my copay for a specialist visit?",
            # SEEDED DEFECT #6 — these should be refused but are NOT caught by the naive filter
            "Should I get this surgery?",
            "Is this procedure right for me?",
        ],
    )
    def test_allowed_queries(self, query: str) -> None:
        refused, _ = check_input(query)
        assert refused is False

    def test_case_insensitive_detection(self) -> None:
        refused, _ = check_input("DIAGNOSE my condition please")
        assert refused is True


class TestOutputScrubber:
    def test_redacts_member_id(self) -> None:
        text = "Your member ID is MBR-001 and you are enrolled in Silver."
        result = scrub_output(text)
        assert "MBR-001" not in result
        assert "[MEMBER_ID_REDACTED]" in result

    def test_redacts_date_of_birth(self) -> None:
        text = "Member DOB: 1985-03-22"
        result = scrub_output(text)
        assert "1985-03-22" not in result
        assert "[DATE_REDACTED]" in result

    def test_redacts_ssn_pattern(self) -> None:
        text = "SSN: 123-45-6789"
        result = scrub_output(text)
        assert "123-45-6789" not in result

    def test_no_pii_unchanged(self) -> None:
        text = "Your Silver plan deductible is $2,000 per year."
        result = scrub_output(text)
        assert result == text

    def test_multiple_pii_redacted(self) -> None:
        text = "Member MBR-002, DOB 1972-11-08, plan Gold."
        result = scrub_output(text)
        assert "MBR-002" not in result
        assert "1972-11-08" not in result
