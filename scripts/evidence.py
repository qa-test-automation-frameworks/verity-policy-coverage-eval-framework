"""Convert native pytest JUnit XML into portfolio evidence v3 records."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPOSITORY = "qa-test-automation-frameworks/verity-policy-coverage-eval-framework"
DEFAULT_OUTPUT = Path("reports/evidence")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SCOPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,199}$")


class EvidenceError(ValueError):
    """Invalid or incomplete native test evidence."""


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_started(value: str | None) -> str:
    if not value:
        raise EvidenceError("EVIDENCE_STARTED_AT is missing")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceError("EVIDENCE_STARTED_AT is invalid") from error
    if parsed.tzinfo is None:
        raise EvidenceError("EVIDENCE_STARTED_AT must include a timezone")
    return parsed.astimezone(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_completed(value: str | None) -> str:
    if not value:
        return utc_now()
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceError("EVIDENCE_COMPLETED_AT is invalid") from error
    if parsed.tzinfo is None:
        raise EvidenceError("EVIDENCE_COMPLETED_AT must include a timezone")
    return parsed.astimezone(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_count(suite: ET.Element, key: str) -> int | None:
    raw = suite.get(key)
    if raw is None:
        return None
    try:
        count = int(raw)
    except ValueError as error:
        raise EvidenceError(f"JUnit {key} count is not an integer") from error
    if count < 0:
        raise EvidenceError(f"JUnit {key} count cannot be negative")
    return count


def parse_junit(path: Path) -> dict[str, Any]:
    """Count final testcase outcomes and reject empty or internally inconsistent reports."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise EvidenceError(f"JUnit report is missing or malformed: {error}") from error

    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = root.findall("testsuite")
    else:
        raise EvidenceError("JUnit root must be <testsuite> or <testsuites>")

    cases: list[ET.Element] = []
    complete = bool(suites)
    suite_case_total = 0
    native_totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        suite_cases = suite.findall("testcase")
        cases.extend(suite_cases)
        suite_case_total += len(suite_cases)
        suite_totals = {
            "tests": len(suite_cases),
            "failures": sum(bool(case.findall("failure")) for case in suite_cases),
            "errors": sum(bool(case.findall("error")) for case in suite_cases),
            "skipped": sum(bool(case.findall("skipped")) for case in suite_cases),
        }
        for key, value in suite_totals.items():
            native_totals[key] += value
        declared = parse_count(suite, "tests")
        if declared is not None and declared != len(suite_cases):
            complete = False
        for key in ("failures", "errors", "skipped"):
            declared_outcome = parse_count(suite, key)
            if declared_outcome is not None and declared_outcome != suite_totals[key]:
                complete = False
    if suite_case_total != len(root.findall(".//testcase")):
        complete = False
    declared_root = parse_count(root, "tests")
    if declared_root is not None and declared_root != len(cases):
        complete = False
    if root.tag == "testsuites":
        for key in ("failures", "errors", "skipped"):
            declared_outcome = parse_count(root, key)
            if declared_outcome is not None and declared_outcome != native_totals[key]:
                complete = False
    if not cases:
        return {"state": "empty", "reason": "JUnit report contained no testcase results"}
    if not complete:
        return {
            "state": "partial",
            "reason": "JUnit suite counts do not reconcile with testcase entries",
        }

    selected = len(cases)
    failed = 0
    skipped = 0
    for case in cases:
        outcome = {child.tag for child in case if child.tag in {"failure", "error", "skipped"}}
        if "failure" in outcome or "error" in outcome:
            failed += 1
        elif "skipped" in outcome:
            skipped += 1
    executed = selected - skipped
    passed = executed - failed
    if min(selected, executed, passed, failed, skipped) < 0 or passed + failed != executed:
        return {"state": "partial", "reason": "JUnit testcase outcomes are inconsistent"}
    return {
        "state": "complete",
        "counts": {
            "unit": "test_case",
            "selected": selected,
            "executed": executed,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "retried": 0,
            "semantics": (
                "JUnit testcase invocations; selected includes skips; errors count as failures."
            ),
        },
    }


def env_record(scope: str, env: Mapping[str, str]) -> dict[str, Any]:
    source_sha = env.get("GITHUB_SHA", "")
    run_id = env.get("GITHUB_RUN_ID", "")
    try:
        attempt = int(env.get("GITHUB_RUN_ATTEMPT", ""))
    except ValueError as error:
        raise EvidenceError("GitHub workflow attempt is missing or invalid") from error
    if not SHA_RE.fullmatch(source_sha) or not run_id.isdigit() or int(run_id) < 1 or attempt < 1:
        raise EvidenceError("GitHub run/source identity is missing or invalid")
    if env.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise EvidenceError("unexpected repository identity")
    if not SCOPE_RE.fullmatch(scope):
        raise EvidenceError("scope is missing or invalid")
    workflow_ref = env.get("GITHUB_WORKFLOW_REF")
    if not workflow_ref:
        raise EvidenceError("GITHUB_WORKFLOW_REF is missing")
    return {
        "schemaVersion": 3,
        "repository": REPOSITORY,
        "sourceSha": source_sha,
        "limitations": [
            (
                "Counts are final pytest testcase outcomes; retries are not separately reported "
                "by pytest JUnit XML."
            ),
            "JUnit testcase names and failure messages are omitted from the portfolio record.",
        ],
        "kind": "execution",
        "workflow": {
            "id": workflow_ref,
            "name": env.get("GITHUB_WORKFLOW", "Verity CI"),
            "runId": run_id,
            "attempt": attempt,
            "url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}",
            "trigger": env.get("GITHUB_EVENT_NAME", "workflow_dispatch"),
            "branch": env.get("GITHUB_REF_NAME", "unknown"),
        },
        "scope": {
            "id": scope,
            "evidenceClass": env.get("EVIDENCE_CLASS", "hermetic"),
            "required": env.get("EVIDENCE_REQUIRED", "true").lower() == "true",
            "freshnessPolicy": env.get("EVIDENCE_FRESHNESS_POLICY", "daily_gate_v1"),
        },
        "target": {
            "identity": env.get("EVIDENCE_TARGET", "verity-evaluation-framework"),
            "revision": env.get("EVIDENCE_TARGET_REVISION", source_sha),
            "fixtureVersion": env.get("EVIDENCE_FIXTURE_VERSION"),
            "environment": env.get("EVIDENCE_ENVIRONMENT", "github-hosted"),
            "profile": env.get("EVIDENCE_PROFILE"),
            "tools": {
                key: env[name]
                for key, name in (
                    ("python", "PYTHON_VERSION"),
                    ("uv", "UV_VERSION"),
                    ("pytest", "PYTEST_VERSION"),
                )
                if env.get(name)
            },
        },
    }


def null_counts(semantics: str) -> dict[str, Any]:
    return {
        "unit": "not_applicable",
        "selected": None,
        "executed": None,
        "passed": None,
        "failed": None,
        "skipped": None,
        "retried": None,
        "semantics": semantics,
    }


def make_record(
    scope: str,
    env: Mapping[str, str],
    junit: Path | None = None,
    skip_reason: str | None = None,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    supplied = sum(value is not None for value in (junit, skip_reason, unavailable_reason))
    if supplied != 1:
        raise EvidenceError(
            "provide exactly one of a JUnit report, skip reason, or unavailable reason"
        )
    record = env_record(scope, env)
    expected_shards = [scope]
    if skip_reason is not None:
        execution = {
            "disposition": "skipped",
            "reason": skip_reason[:500],
            "startedAt": None,
            "completedAt": None,
            "integrity": "empty",
            "counts": null_counts(
                "Credentialed evaluation was not requested or no provider key was configured."
            ),
            "measurements": [],
            "shards": {"expected": expected_shards, "received": []},
        }
    elif unavailable_reason is not None:
        execution = {
            "disposition": "unavailable",
            "reason": unavailable_reason[:500],
            "startedAt": parse_started(env.get("EVIDENCE_STARTED_AT")),
            "completedAt": parse_completed(env.get("EVIDENCE_COMPLETED_AT")),
            "integrity": "unavailable",
            "counts": null_counts(
                "Test execution was attempted but native results were unavailable."
            ),
            "measurements": [],
            "shards": {"expected": expected_shards, "received": []},
        }
    else:
        try:
            results = parse_junit(junit)  # type: ignore[arg-type]
        except EvidenceError as error:
            results = {"state": "unavailable", "reason": str(error)}
        if results["state"] == "complete":
            counts = results["counts"]
            disposition = "failed" if counts["failed"] > 0 else "passed"
            execution = {
                "disposition": disposition,
                "reason": f"{counts['failed']} pytest testcase(s) failed"
                if disposition == "failed"
                else None,
                "startedAt": parse_started(env.get("EVIDENCE_STARTED_AT")),
                "completedAt": parse_completed(env.get("EVIDENCE_COMPLETED_AT")),
                "integrity": "complete",
                "counts": counts,
                "measurements": [],
                "shards": {"expected": expected_shards, "received": expected_shards},
            }
        else:
            state = results["state"]
            execution = {
                "disposition": "unavailable",
                "reason": results["reason"][:500],
                "startedAt": parse_started(env.get("EVIDENCE_STARTED_AT")),
                "completedAt": parse_completed(env.get("EVIDENCE_COMPLETED_AT")),
                "integrity": "empty"
                if state == "empty"
                else "partial"
                if state == "partial"
                else "unavailable",
                "counts": {
                    "unit": "test_case",
                    "selected": 0 if state == "empty" else None,
                    "executed": 0 if state == "empty" else None,
                    "passed": 0 if state == "empty" else None,
                    "failed": 0 if state == "empty" else None,
                    "skipped": 0 if state == "empty" else None,
                    "retried": 0 if state == "empty" else None,
                    "semantics": (
                        "JUnit testcase invocations; no result counts are asserted when report "
                        "integrity is incomplete."
                    ),
                },
                "measurements": [],
                "shards": {"expected": expected_shards, "received": []},
            }
    record.update(
        {
            "execution": execution,
            "publication": {
                "disposition": "pending",
                "reason": (
                    "This immutable execution record was emitted before the trusted publisher "
                    "completed; consult the durable latest index for final publication status."
                ),
                "publishedAt": None,
                "reportUrl": None,
                "artifacts": [],
            },
            "generator": {"name": "verity-pytest-junit-evidence", "version": "1.0.0"},
        }
    )
    return record


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--scope", required=True)
    result.add_argument("--junit", type=Path)
    result.add_argument("--skip-reason")
    result.add_argument("--unavailable-reason")
    result.add_argument("--output", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    output = (
        args.output or DEFAULT_OUTPUT / f"{args.scope.replace('/', '_').replace(':', '_')}.json"
    )
    try:
        record = make_record(
            args.scope,
            os.environ,
            junit=args.junit,
            skip_reason=args.skip_reason,
            unavailable_reason=args.unavailable_reason,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    except (EvidenceError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(f"{output}: {record['execution']['disposition']}")
    return 1 if record["execution"]["disposition"] == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
