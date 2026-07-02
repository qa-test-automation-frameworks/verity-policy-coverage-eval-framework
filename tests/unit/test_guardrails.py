"""Unit tests for SUT guardrails."""

from __future__ import annotations

import logging

import pytest

from sut.guardrails import check_input, log_member_context, scrub_output
from verity.checks import scan_log_pii, scan_pii


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


class TestOutputScrubberPreservesNonPiiDates:
    """A bare ISO date is not automatically a date of birth — the scrubber and
    scan_pii must not flag/redact a policy effective date that carries no
    birth-context wording nearby."""

    def test_policy_effective_date_not_redacted(self) -> None:
        text = "The Silver premium is $445, effective 2024-07-01 per Amendment A1."
        result = scrub_output(text)
        assert "2024-07-01" in result
        assert "[DATE_REDACTED]" not in result

    def test_policy_effective_date_not_flagged_as_pii(self) -> None:
        text = "The Silver premium is $445, effective 2024-07-01 per Amendment A1."
        assert scan_pii(text) == []

    def test_dob_still_redacted_with_context(self) -> None:
        text = "Your date of birth on file is 1985-03-22."
        result = scrub_output(text)
        assert "1985-03-22" not in result
        assert "[DATE_REDACTED]" in result

    def test_dob_still_flagged_as_pii_with_context(self) -> None:
        text = "I have your information: date of birth on file is 1985-03-22."
        assert any("date-of-birth" in hit for hit in scan_pii(text))


class TestPIILogLeak:
    """Defect #8 — log_member_context writes raw PII to DEBUG log (the real leak site)."""

    def test_log_member_context_emits_raw_pii(self, caplog: pytest.LogCaptureFixture) -> None:
        member = {"member_id": "MBR-001", "name": "Alice Hartwell", "dob": "1985-03-22"}
        with caplog.at_level(logging.DEBUG, logger="sut.guardrails"):
            log_member_context(member)
        findings = scan_log_pii([r.message for r in caplog.records], member_name="Alice Hartwell")
        assert any("name:Alice Hartwell" in hit for hit in findings), (
            "Expected raw member name in DEBUG log — seeded defect #8 leak site should emit PII"
        )
        assert any("member-id:MBR-001" in hit for hit in findings), (
            "Expected raw member_id in DEBUG log"
        )

    def test_log_member_context_emits_dob(self, caplog: pytest.LogCaptureFixture) -> None:
        member = {"member_id": "MBR-002", "name": "Bob Torres", "dob": "1972-11-08"}
        with caplog.at_level(logging.DEBUG, logger="sut.guardrails"):
            log_member_context(member)
        findings = scan_log_pii([r.message for r in caplog.records])
        assert any("date-of-birth:1972-11-08" in hit for hit in findings), (
            "Expected raw DOB in DEBUG log — confirms log-level PII exposure"
        )


class TestScrubBeforeCheck:
    """Defect #8 — scrub_output runs before check_pii reads response.answer.

    The output scrubber masks MBR-id and DOB patterns in the response text
    before check_pii evaluates it, so only an echoed member name can be caught
    at the response level. These tests document that ordering explicitly.
    """

    def test_scrubber_masks_member_id_before_pii_check(self) -> None:
        raw_answer = "Your member ID is MBR-042 and your deductible is $2,000."
        scrubbed = scrub_output(raw_answer)
        # After scrubbing, check_pii must not find the member-id pattern
        pii_hits = scan_pii(scrubbed)
        assert not any("member-id" in hit for hit in pii_hits), (
            "scrub_output should have already masked MBR-id before check_pii sees it"
        )

    def test_scrubber_masks_dob_before_pii_check(self) -> None:
        raw_answer = "Your date of birth on file is 1985-03-22."
        scrubbed = scrub_output(raw_answer)
        pii_hits = scan_pii(scrubbed)
        assert not any("date-of-birth" in hit for hit in pii_hits), (
            "scrub_output should have already masked DOB before check_pii sees it"
        )

    def test_member_name_not_scrubbed_by_output_scrubber(self) -> None:
        raw_answer = "Hello Alice Hartwell, your plan covers this procedure."
        scrubbed = scrub_output(raw_answer)
        # The scrubber has no name-pattern rule — name passes through unmasked
        assert "Alice Hartwell" in scrubbed, (
            "scrub_output does not redact member names; check_pii catches them via member_name arg"
        )
        pii_hits = scan_pii(scrubbed, member_name="Alice Hartwell")
        assert any("name:" in hit for hit in pii_hits), (
            "check_pii should detect the echoed name when member_name is provided"
        )
