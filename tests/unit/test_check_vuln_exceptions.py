"""Unit tests for the vulnerability exception expiry gate script."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts.check_vuln_exceptions import check_vuln_exceptions


def _write(tmp_path: Path, content: str) -> Path:
    out = tmp_path / ".pip-audit-ignore"
    out.write_text(content)
    return out


class TestCheckVulnExceptions:
    def test_unexpired_entry_passes(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "# Expires: 2099-01-01\nCVE-2099-0001\n",
        )
        assert check_vuln_exceptions(path, today=date(2026, 7, 2)) == []

    def test_expired_entry_fails(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "# Expires: 2026-01-01\nCVE-2026-0001\n",
        )
        failures = check_vuln_exceptions(path, today=date(2026, 7, 2))
        assert len(failures) == 1
        assert "CVE-2026-0001" in failures[0]
        assert "expired" in failures[0]

    def test_entry_expiring_today_passes(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "# Expires: 2026-07-02\nCVE-2026-0002\n",
        )
        assert check_vuln_exceptions(path, today=date(2026, 7, 2)) == []

    def test_entry_without_expiry_comment_fails(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "CVE-2026-0003\n")
        failures = check_vuln_exceptions(path, today=date(2026, 7, 2))
        assert len(failures) == 1
        assert "no `Expires" in failures[0]

    def test_blank_line_resets_pending_expiry(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "# Expires: 2099-01-01\n\nCVE-2026-0004\n",
        )
        failures = check_vuln_exceptions(path, today=date(2026, 7, 2))
        assert len(failures) == 1
        assert "CVE-2026-0004" in failures[0]

    def test_multiple_entries_each_checked_independently(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "# Expires: 2099-01-01\nCVE-A\n#\n# Expires: 2020-01-01\nCVE-B\n",
        )
        failures = check_vuln_exceptions(path, today=date(2026, 7, 2))
        assert len(failures) == 1
        assert "CVE-B" in failures[0]

    def test_expiry_cannot_be_reused_by_another_entry(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "# Expires: 2099-01-01\nCVE-FIRST\nCVE-SECOND\n")
        failures = check_vuln_exceptions(path, today=date(2026, 10, 4))
        assert len(failures) == 1
        assert "CVE-SECOND: no `Expires" in failures[0]

    def test_invalid_calendar_date_is_a_gate_failure(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "# Expires: 2026-02-30\nCVE-FIRST\n")
        failures = check_vuln_exceptions(path, today=date(2026, 10, 4))
        assert any("invalid Expires" in failure for failure in failures)
        assert any("CVE-FIRST: no `Expires" in failure for failure in failures)

    def test_malformed_date_cannot_reuse_earlier_valid_date(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "# Expires: 2099-01-01\n# Expires: next-quarter\nCVE-FIRST\n")
        failures = check_vuln_exceptions(path, today=date(2026, 10, 4))
        assert any("invalid Expires" in failure for failure in failures)
        assert any("no `Expires" in failure for failure in failures)

    def test_malformed_bare_line_is_not_silently_ignored(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "# Expires: 2099-01-01\nCVE-FIRST extra-argument\n")
        assert "malformed vulnerability ID" in check_vuln_exceptions(path, date(2026, 10, 4))[0]

    def test_duplicate_exclusion_is_rejected(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path, "# Expires: 2099-01-01\nCVE-FIRST\n# Expires: 2099-01-01\nCVE-FIRST\n"
        )
        assert any(
            "duplicate exception" in failure
            for failure in check_vuln_exceptions(path, date(2026, 10, 4))
        )

    def test_no_active_exclusions_is_valid(self, tmp_path: Path) -> None:
        assert (
            check_vuln_exceptions(_write(tmp_path, "# No active exclusions.\n"), date(2026, 10, 4))
            == []
        )
