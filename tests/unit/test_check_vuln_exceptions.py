"""Unit tests for the vulnerability exception expiry gate script."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts.check_vuln_exceptions import check_vuln_exceptions


def _write(tmp_path: Path, content: str, name: str = ".pip-audit-ignore") -> Path:
    out = tmp_path / name
    record = tmp_path / "docs" / "security" / "review.md"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(content)
    out.write_text(content)
    return out


def _entry(vuln_id: str, *, reviewed: str = "2026-10-19", expires: str = "2026-11-17") -> str:
    return (
        f"# Reviewed: {reviewed}\n"
        "# Reviewer: independent reviewer and owner\n"
        "# Record: docs/security/review.md\n"
        "# Decision: retain until recorded expiry; do not renew automatically\n"
        f"# Expires: {expires}\n"
        f"{vuln_id}\n"
    )


class TestCheckVulnExceptions:
    def test_reviewed_entry_within_maximum_window_passes(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _entry("PYSEC-2026-2447"))
        assert check_vuln_exceptions(path, today=date(2026, 10, 19)) == []

    def test_expiry_day_fails_closed(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _entry("CVE-2026-0001", expires="2026-10-19"))
        failures = check_vuln_exceptions(path, today=date(2026, 10, 19))
        assert any("expired" in failure for failure in failures)

    def test_expired_entry_fails(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            _entry("CVE-2026-0002", reviewed="2026-09-01", expires="2026-10-18"),
        )
        assert any(
            "expired" in failure for failure in check_vuln_exceptions(path, date(2026, 10, 19))
        )

    def test_review_window_longer_than_30_days_fails(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            _entry("CVE-2026-0003", reviewed="2026-10-01", expires="2026-11-01"),
        )
        assert any(
            "exceeds 30 days" in failure
            for failure in check_vuln_exceptions(path, date(2026, 10, 19))
        )

    def test_future_review_date_fails(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            _entry("CVE-2026-0004", reviewed="2026-10-20", expires="2026-11-19"),
        )
        assert any(
            "in the future" in failure
            for failure in check_vuln_exceptions(path, date(2026, 10, 19))
        )

    def test_expiry_must_follow_review(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            _entry("CVE-2026-0005", reviewed="2026-10-19", expires="2026-10-18"),
        )
        assert any(
            "must be after" in failure
            for failure in check_vuln_exceptions(path, date(2026, 10, 19))
        )

    def test_missing_reviewer_fails(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "# Reviewed: 2026-10-19\n# Record: docs/security/review.md\n"
            "# Decision: retain until expiry\n"
            "# Expires: 2026-11-17\nPYSEC-2026-2447\n",
        )
        assert any(
            "reviewer" in failure for failure in check_vuln_exceptions(path, date(2026, 10, 19))
        )

    def test_missing_review_date_fails(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "# Reviewer: reviewer\n# Record: docs/security/review.md\n"
            "# Decision: retain until expiry\n"
            "# Expires: 2026-11-17\nPYSEC-2026-2447\n",
        )
        assert any(
            "reviewed" in failure for failure in check_vuln_exceptions(path, date(2026, 10, 19))
        )

    def test_expiry_metadata_cannot_be_shared_by_multiple_ids(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            _entry("PYSEC-2026-2447") + "PYSEC-2026-3046\n",
        )
        assert any(
            "PYSEC-2026-3046" in failure
            for failure in check_vuln_exceptions(path, date(2026, 10, 19))
        )

    def test_dangling_review_metadata_fails(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _entry("PYSEC-2026-2447").rsplit("\n", 2)[0] + "\n")
        assert any(
            "not followed" in failure for failure in check_vuln_exceptions(path, date(2026, 10, 19))
        )

    def test_review_record_must_exist(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path, _entry("CVE-2026-0007").replace("docs/security/review.md", "missing.md")
        )
        assert any(
            "does not exist" in failure
            for failure in check_vuln_exceptions(path, date(2026, 10, 19))
        )

    def test_trivy_ignore_uses_same_review_policy(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _entry("CVE-2026-0006"), name=".trivyignore")
        assert check_vuln_exceptions(path, today=date(2026, 10, 19)) == []
