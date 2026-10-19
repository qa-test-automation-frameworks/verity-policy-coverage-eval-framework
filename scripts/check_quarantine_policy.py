"""Validate bounded, traceable live-metric quarantines without executing live tests."""

from __future__ import annotations

import ast
import re
import sys
from datetime import date
from pathlib import Path

import yaml


def _local_path(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = (root / value).resolve()
    if not candidate.is_relative_to(root.resolve()) or not candidate.is_file():
        return None
    return candidate


def _is_quarantined(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        ast.unparse(decorator.func if isinstance(decorator, ast.Call) else decorator)
        == "pytest.mark.quarantine"
        for decorator in function.decorator_list
    )


def check_quarantine_policy(path: Path, root: Path, today: date) -> list[str]:
    """Return policy failures; missing dependencies remain errors rather than success."""
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as error:
        return [f"Quarantine manifest cannot be read: {type(error).__name__}"]
    if (
        not isinstance(data, dict)
        or type(data.get("schemaVersion")) is not int
        or data.get("schemaVersion") != 1
    ):
        return ["Quarantine manifest requires schemaVersion 1"]
    items = data.get("items")
    if not isinstance(items, list):
        return ["Quarantine items must be a list"]
    failures: list[str] = []
    policy = data.get("policy")
    if not isinstance(policy, dict):
        failures.append("Quarantine policy settings must be an object")
        policy = {}
    if not isinstance(policy.get("summary"), str) or not policy["summary"].strip():
        failures.append("Quarantine policy requires a nonempty summary")
    if not isinstance(policy.get("reviewCadence"), str) or not policy["reviewCadence"].strip():
        failures.append("Quarantine policy requires an explicit reviewCadence")
    limits: dict[str, int] = {}
    for field in ("maxReviewDays", "maxExpiryDays"):
        value = policy.get(field)
        if type(value) is not int or value < 1:
            failures.append(f"Quarantine policy requires positive integer {field}")
            limits[field] = 0
        else:
            limits[field] = value
    seen: set[str] = set()
    covered_tests: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            failures.append("Quarantine entry must be an object")
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
            failures.append("Quarantine ID is missing or duplicated")
        else:
            seen.add(identifier)
        prefix = str(identifier)
        for field in (
            "ownerRole",
            "reviewedBy",
            "reviewDisposition",
            "reason",
            "promotionCriteria",
        ):
            if not isinstance(item.get(field), str) or not item[field].strip():
                failures.append(f"{prefix}: missing {field}")
        if item.get("reviewDisposition") != "retain":
            failures.append(f"{prefix}: active quarantine reviewDisposition must be 'retain'")
        if item.get("status") != "active":
            failures.append(f"{prefix}: unsupported status; archive inactive entries")
        dates: dict[str, date] = {}
        for field in ("reviewedOn", "reviewDue", "expires"):
            value = item.get(field)
            try:
                if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError("Dates must use YYYY-MM-DD strings")
                dates[field] = date.fromisoformat(value)
            except ValueError:
                failures.append(f"{prefix}: invalid {field}")
        if len(dates) == 3:
            reviewed, due, expires = (
                dates[name] for name in ("reviewedOn", "reviewDue", "expires")
            )
            if not reviewed <= today <= due <= expires:
                failures.append(f"{prefix}: review is overdue, expired or has inconsistent dates")
            if (due - reviewed).days > limits["maxReviewDays"] or (
                expires - reviewed
            ).days > limits["maxExpiryDays"]:
                failures.append(
                    f"{prefix}: review/expiry window exceeds policy limits "
                    f"({limits['maxReviewDays']}/{limits['maxExpiryDays']} days)"
                )
        source = _local_path(root, item.get("source"))
        if (
            item.get("source") != "docs/known-issues.md"
            or source is None
            or not isinstance(identifier, str)
            or identifier not in source.read_text()
        ):
            failures.append(
                f"{prefix}: source must reference this issue in a repository-local file"
            )
        tests = item.get("tests")
        if not isinstance(tests, list) or not tests:
            failures.append(f"{prefix}: exact tests must be a nonempty list")
            continue
        if any(not isinstance(node_id, str) for node_id in tests):
            failures.append(f"{prefix}: exact test references must be strings")
        elif len(set(tests)) != len(tests):
            failures.append(f"{prefix}: duplicate exact test reference")
        for node_id in tests:
            if isinstance(node_id, str):
                covered_tests.add(node_id)
            parts = node_id.split("::") if isinstance(node_id, str) else []
            test_path = _local_path(root, parts[0]) if len(parts) == 2 else None
            if test_path is None:
                failures.append(f"{prefix}: invalid repository-local test ID")
                continue
            try:
                functions = [
                    node
                    for node in ast.walk(ast.parse(test_path.read_text()))
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == parts[1]
                ]
                if not functions:
                    failures.append(f"{prefix}: named test does not exist: {node_id}")
                elif not any(_is_quarantined(function) for function in functions):
                    failures.append(f"{prefix}: named test has no quarantine marker: {node_id}")
            except (OSError, SyntaxError):
                failures.append(f"{prefix}: named test cannot be inspected: {node_id}")
    # Removing a manifest entry must not leave an undated live metric quarantine.
    for source_path in (root / "tests/semantic").rglob("test_*.py"):
        try:
            tree = ast.parse(source_path.read_text())
        except (OSError, SyntaxError):
            failures.append("Semantic quarantine markers cannot be inspected")
            continue
        for function in ast.walk(tree):
            if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_quarantined(
                function
            ):
                node_id = f"{source_path.relative_to(root).as_posix()}::{function.name}"
                if node_id not in covered_tests:
                    failures.append(f"Untracked quarantine marker: {node_id}")
    return failures


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "reliability/quarantine.yml"
    failures = check_quarantine_policy(manifest, root, date.today())
    if failures:
        for failure in failures:
            print(failure)
        sys.exit(1)
    print("Quarantine metadata is valid; ownership acceptance and live promotion remain unproven.")


if __name__ == "__main__":
    main()
