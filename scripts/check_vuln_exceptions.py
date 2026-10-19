"""Fail CI when an exception lacks review metadata, is expired, or is too long.

Each ignored vulnerability ID must immediately follow its own Reviewed,
Reviewer, Review-by, and Expires metadata. Exceptions must be reassessed within
14 days and expire within 30 days. The expiry date itself is no longer an
accepted day. Metadata is consumed by one ID only; it cannot silently
authorize later entries.

Usage:
    uv run python scripts/check_vuln_exceptions.py [ignore-file ...]

With no paths, both `.pip-audit-ignore` and `.trivyignore` are checked.
"""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

_EXPIRES_RE = re.compile(r"^#\s*Expires:\s*(\d{4}-\d{2}-\d{2})\s*$")
_REVIEWED_RE = re.compile(r"^#\s*Reviewed:\s*(\d{4}-\d{2}-\d{2})\s*$")
_REVIEW_BY_RE = re.compile(r"^#\s*Review-by:\s*(\d{4}-\d{2}-\d{2})\s*$")
_REVIEWER_RE = re.compile(r"^#\s*Reviewer:\s*(\S.*)$")
_RECORD_RE = re.compile(r"^#\s*Record:\s*(\S.*)$")
_DECISION_RE = re.compile(r"^#\s*Decision:\s*(\S.*)$")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
MAX_REVIEW_WINDOW_DAYS = 30
MAX_REASSESSMENT_WINDOW_DAYS = 14


def check_vuln_exceptions(path: Path, today: date) -> list[str]:
    """Return a list of failure messages (empty if every entry is unexpired and dated)."""
    lines = path.read_text().splitlines()

    failures: list[str] = []
    pending: dict[str, str] = {}

    def report_dangling_metadata(line_number: int) -> None:
        if pending:
            failures.append(
                f"line {line_number}: review metadata is not followed by exactly one "
                "vulnerability ID"
            )

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            report_dangling_metadata(line_number)
            pending.clear()
            continue
        if stripped.startswith("#"):
            for key, pattern in (
                ("reviewed", _REVIEWED_RE),
                ("review_by", _REVIEW_BY_RE),
                ("reviewer", _REVIEWER_RE),
                ("record", _RECORD_RE),
                ("decision", _DECISION_RE),
                ("expires", _EXPIRES_RE),
            ):
                match = pattern.match(stripped)
                if match:
                    if key in pending:
                        failures.append(f"line {line_number}: duplicate {key} metadata")
                    else:
                        pending[key] = match.group(1)
                    break
            continue
        if not _ID_RE.match(stripped):
            failures.append(f"line {line_number}: malformed exception entry {stripped!r}")
            continue
        vuln_id = stripped
        missing = {
            "reviewed",
            "review_by",
            "reviewer",
            "record",
            "decision",
            "expires",
        } - pending.keys()
        if missing:
            failures.append(f"{vuln_id}: missing required metadata: {', '.join(sorted(missing))}")
        if "record" in pending:
            record_path = Path(pending["record"])
            if record_path.is_absolute() or ".." in record_path.parts:
                failures.append(f"{vuln_id}: review record path must stay inside the repository")
            elif not (path.parent / record_path).is_file():
                failures.append(f"{vuln_id}: review record {record_path} does not exist")
            else:
                record_text = " ".join((path.parent / record_path).read_text().split())
                for required_text in (
                    vuln_id,
                    pending.get("reviewed", ""),
                    pending.get("review_by", ""),
                    pending.get("expires", ""),
                    pending.get("reviewer", ""),
                    pending.get("decision", ""),
                ):
                    normalized = " ".join(required_text.split())
                    if normalized and normalized not in record_text:
                        failures.append(f"{vuln_id}: review record does not contain {normalized!r}")
        if {"reviewed", "review_by", "expires"} <= pending.keys():
            try:
                reviewed = date.fromisoformat(pending["reviewed"])
                review_by = date.fromisoformat(pending["review_by"])
                expires = date.fromisoformat(pending["expires"])
            except ValueError:
                failures.append(f"{vuln_id}: review or expiry date is invalid")
            else:
                if reviewed > today:
                    failures.append(
                        f"{vuln_id}: review date {reviewed.isoformat()} is in the future"
                    )
                if review_by < today:
                    failures.append(f"{vuln_id}: review deadline passed on {review_by.isoformat()}")
                if review_by <= reviewed:
                    failures.append(f"{vuln_id}: review deadline must follow the review date")
                elif review_by - reviewed > timedelta(days=MAX_REASSESSMENT_WINDOW_DAYS):
                    failures.append(
                        f"{vuln_id}: reassessment window exceeds "
                        f"{MAX_REASSESSMENT_WINDOW_DAYS} days"
                    )
                if review_by >= expires:
                    failures.append(f"{vuln_id}: review deadline must be before expiry")
                if expires <= today:
                    failures.append(f"{vuln_id}: exception expired on {expires.isoformat()}")
                if expires <= reviewed:
                    failures.append(f"{vuln_id}: expiry must be after the review date")
                elif expires - reviewed > timedelta(days=MAX_REVIEW_WINDOW_DAYS):
                    failures.append(
                        f"{vuln_id}: review window exceeds {MAX_REVIEW_WINDOW_DAYS} days"
                    )
        pending.clear()

    report_dangling_metadata(len(lines) + 1)

    return failures


def main() -> None:
    ignore_paths = (
        [Path(arg) for arg in sys.argv[1:]]
        if len(sys.argv) > 1
        else [Path(".pip-audit-ignore"), Path(".trivyignore")]
    )
    failures: list[str] = []
    for path in ignore_paths:
        if not path.is_file():
            failures.append(f"{path}: required exception file is missing")
            continue
        failures.extend(
            f"{path}: {failure}" for failure in check_vuln_exceptions(path, date.today())
        )

    if failures:
        print("Vulnerability exception check FAILED:")
        for f in failures:
            print(f"  - {f}")
        print("Re-evaluate the affected dependency and update the relevant scanner ignore file.")
        raise SystemExit(1)

    print("All accepted vulnerability exceptions are dated and unexpired.")


if __name__ == "__main__":
    main()
