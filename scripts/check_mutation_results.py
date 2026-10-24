"""Fail when mutmut leaves killable mutants alive.

mutmut exits 0 from `run` and `results` even when mutants survive, so this reads
`mutmut export-cicd-stats` and `mutmut results` and decides the exit code:

  0  every mutant was killed, or the survivor is in an unexpired allowlist entry
  1  a mutant survived, timed out, was suspicious, crashed or had no tests
  2  the input was not in a recognised format (fail closed)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

STATS_KEYS = (
    "killed",
    "survived",
    "total",
    "no_tests",
    "skipped",
    "suspicious",
    "timeout",
    "check_was_interrupted_by_user",
    "segfault",
)
# results status text -> stats key
FAILING_STATUSES = {
    "survived": "survived",
    "timeout": "timeout",
    "suspicious": "suspicious",
    "segfault": "segfault",
    "no tests": "no_tests",
}
IGNORED_STATUSES = {"killed", "skipped"}
LINE = re.compile(r"^\s*(?P<name>\S+): (?P<status>.+?)\s*$")
MAX_ALLOWLIST_DAYS = 90


class FormatError(Exception):
    """Input is not in a format this checker recognises."""


def _load_stats(path: Path) -> dict[str, int]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FormatError(f"unrecognised mutmut stats format: {exc}") from exc
    if not isinstance(data, dict) or any(key not in data for key in STATS_KEYS):
        raise FormatError("unrecognised mutmut stats format")
    for key in STATS_KEYS:
        value = data[key]
        if key == "check_was_interrupted_by_user" and isinstance(value, bool):
            continue
        if type(value) is not int or value < 0:
            raise FormatError(f"unrecognised mutmut stats value for {key}")
    counts = sum(
        data[key] for key in STATS_KEYS if key not in {"total", "check_was_interrupted_by_user"}
    )
    if counts != data["total"]:
        raise FormatError("mutmut stats total does not reconcile")
    return {key: int(data[key]) for key in STATS_KEYS}


def _parse_results(text: str) -> dict[str, str]:
    mutants: dict[str, str] = {}
    for raw in text.splitlines():
        if not raw.strip():
            continue
        match = LINE.match(raw)
        if not match:
            raise FormatError(f"unrecognised mutmut results line: {raw!r}")
        status = match["status"]
        if status not in FAILING_STATUSES and status not in IGNORED_STATUSES:
            raise FormatError(f"unrecognised mutant status {status!r} for {match['name']}")
        if match["name"] in mutants:
            raise FormatError(f"duplicate mutant {match['name']}")
        mutants[match["name"]] = status
    return mutants


def _load_allowlist(path: Path) -> list[dict[str, Any]]:
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FormatError(f"unreadable allowlist {path}: {exc}") from exc
    if not isinstance(entries, list):
        raise FormatError("allowlist must be a JSON array")
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or any(
            not isinstance(entry.get(key), str) or not entry[key].strip()
            for key in ("mutant", "status", "reason", "reviewedOn", "expiresOn")
        ):
            raise FormatError(
                "allowlist entries need mutant, status, reason, reviewedOn, expiresOn"
            )
        if entry["mutant"] in names:
            raise FormatError(f"duplicate allowlist entry {entry['mutant']}")
        names.add(entry["mutant"])
        if entry["status"] not in FAILING_STATUSES:
            raise FormatError(f"invalid allowlist status for {entry['mutant']}")
        try:
            reviewed = date.fromisoformat(entry["reviewedOn"])
            expires = date.fromisoformat(entry["expiresOn"])
        except ValueError as exc:
            raise FormatError(f"bad date in allowlist entry {entry['mutant']}") from exc
        if expires < reviewed:
            raise FormatError(f"expiry precedes review for {entry['mutant']}")
        if expires - reviewed > timedelta(days=MAX_ALLOWLIST_DAYS):
            raise FormatError(
                f"allowlist entry {entry['mutant']} exceeds {MAX_ALLOWLIST_DAYS} days"
            )
    return entries


def check(
    stats: dict[str, int], mutants: dict[str, str], allowlist: list[dict[str, Any]], today: date
) -> tuple[int, list[str]]:
    """Return (exit code, output lines). Raises FormatError for exit 2."""
    counts = Counter(mutants.values())
    for status, key in FAILING_STATUSES.items():
        if counts.get(status, 0) != stats[key]:
            raise FormatError(
                f"count mismatch for {status}: results list {counts.get(status, 0)}, "
                f"stats report {stats[key]}"
            )
    lines: list[str] = []
    failures: list[str] = []
    if stats["check_was_interrupted_by_user"]:
        failures.append("mutation run was interrupted")
    if stats["total"] == 0 or stats["killed"] == 0:
        failures.append("no mutants executed")
    lines.append(f"{stats['killed']}/{stats['total']} mutants killed")

    failing = {name: status for name, status in mutants.items() if status in FAILING_STATUSES}
    for entry in allowlist:
        name = entry["mutant"]
        if date.fromisoformat(entry["reviewedOn"]) > today:
            failures.append(f"allowlist review for {name} is in the future")
        elif name in failing and entry["status"] != failing[name]:
            failures.append(f"allowlist status mismatch for {name}")
        elif date.fromisoformat(entry["expiresOn"]) < today:
            failures.append(f"allowlist entry for {name} expired on {entry['expiresOn']}")
        elif name not in failing:
            failures.append(f"stale allowlist entry {name}; remove it")
        else:
            lines.append(f"allowlisted: {name}: {failing.pop(name)} ({entry['reason']})")
    failures.extend(f"{name}: {status}" for name, status in sorted(failing.items()))
    skipped = sum(1 for status in mutants.values() if status == "skipped")
    if skipped:
        lines.append(f"{skipped} mutants skipped (not failing)")
    lines.extend(failures)
    return (1 if failures else 0), lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stats", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--today", type=date.fromisoformat, default=None)
    args = parser.parse_args(argv)
    try:
        stats = _load_stats(args.stats)
        mutants = _parse_results(args.results.read_text(encoding="utf-8"))
        allowlist = _load_allowlist(args.allowlist)
        code, lines = check(stats, mutants, allowlist, args.today or date.today())
    except (FormatError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
