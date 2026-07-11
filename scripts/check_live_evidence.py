"""Fail live evidence generation when failures are not explicitly owned and bounded."""

from __future__ import annotations

import fnmatch
import json
from datetime import date
from pathlib import Path


def check(results_path: Path, exceptions_path: Path) -> list[str]:
    results = json.loads(results_path.read_text(encoding="utf-8"))
    exceptions = json.loads(exceptions_path.read_text(encoding="utf-8"))["exceptions"]
    failures = [node for node, outcome in results.get("outcomes", {}).items() if outcome == "failed"]
    errors: list[str] = []
    for exception in exceptions:
        if not exception.get("owner") or not exception.get("expires") or not exception.get("reason"):
            errors.append(f"Invalid exception metadata: {exception}")
        elif date.fromisoformat(exception["expires"]) < date.today():
            errors.append(f"Expired live-evidence exception: {exception['pattern']}")
    for failure in failures:
        if not any(fnmatch.fnmatch(failure, exception["pattern"] + "*") for exception in exceptions):
            errors.append(f"Unowned live-evidence failure: {failure}")
    return errors


if __name__ == "__main__":
    problems = check(Path("reports/semantic/results.json"), Path("docs/evidence/live-exceptions.json"))
    if problems:
        raise SystemExit("\n".join(problems))
    print("All live-evidence failures are explicitly owned and unexpired.")
