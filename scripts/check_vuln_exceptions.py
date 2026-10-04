"""Fail CI when an accepted dependency vulnerability exception has expired.

.pip-audit-ignore accepts specific CVE/PYSEC IDs indefinitely unless something
forces a re-review. This script parses the `Expires: YYYY-MM-DD` comment
attached to each ID and fails once that date has passed, so an accepted risk
can't silently outlive its review window.

Usage:
    uv run python scripts/check_vuln_exceptions.py [.pip-audit-ignore]
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

_EXPIRES_RE = re.compile(r"^#\s*Expires:\s*(\d{4}-\d{2}-\d{2})\s*$")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def check_vuln_exceptions(path: Path, today: date) -> list[str]:
    """Return a list of failure messages (empty if every entry is unexpired and dated)."""
    lines = path.read_text().splitlines()

    failures: list[str] = []
    pending_expiry: date | None = None
    seen_ids: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            pending_expiry = None
            continue
        if stripped.startswith("#"):
            if re.match(r"^#\s*Expires:", stripped):
                expires_match = _EXPIRES_RE.fullmatch(stripped)
                pending_expiry = None
                try:
                    if not expires_match:
                        raise ValueError("Expected YYYY-MM-DD")
                    pending_expiry = date.fromisoformat(expires_match.group(1))
                except ValueError:
                    failures.append(f"line {line_number}: invalid Expires date")
            continue
        if not _ID_RE.fullmatch(stripped):
            failures.append(f"line {line_number}: malformed vulnerability ID")
            pending_expiry = None
            continue
        vuln_id = stripped
        if vuln_id in seen_ids:
            failures.append(f"{vuln_id}: duplicate exception")
        seen_ids.add(vuln_id)
        if pending_expiry is None:
            failures.append(f"{vuln_id}: no `Expires: YYYY-MM-DD` comment found before this entry")
        elif pending_expiry < today:
            failures.append(f"{vuln_id}: exception expired on {pending_expiry.isoformat()}")
        # Each bare ID must have its own date; one comment cannot exempt later IDs.
        pending_expiry = None

    return failures


def main() -> None:
    ignore_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".pip-audit-ignore")
    failures = check_vuln_exceptions(ignore_path, date.today())

    if failures:
        print("Vulnerability exception check FAILED:")
        for f in failures:
            print(f"  - {f}")
        print("Re-evaluate the affected dependency and update .pip-audit-ignore.")
        raise SystemExit(1)

    print("All accepted vulnerability exceptions are dated and unexpired.")


if __name__ == "__main__":
    main()
