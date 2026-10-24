"""Authored calibration inputs must not impersonate a provider measurement."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def fixture_problems(payload: dict) -> list[str]:
    problems = []
    if payload.get("model") != "authored-fixture":
        problems.append("Authored cassette must identify an authored fixture")
    usage = payload.get("usage")
    if usage is not None and (
        not isinstance(usage, dict)
        or set(usage) != {"prompt_tokens", "completion_tokens", "total_tokens"}
        or any(type(value) is not int or value != 0 for value in usage.values())
    ):
        problems.append("Authored cassette must not claim provider token usage")
    return problems


def measurement_table(readme: str) -> str:
    heading = "## Calibration measurements"
    if heading not in readme:
        raise ValueError("Calibration measurements heading is missing")
    section = readme.split(heading, 1)[1]
    section = re.split(r"\n#{1,3} ", section, maxsplit=1)[0]
    rows = [line for line in section.splitlines() if line.startswith("|")]
    if len(rows) < 3:
        raise ValueError("Calibration measurements table is missing")
    return "\n".join(rows)


def test_authored_cassettes_are_explicit_fixtures() -> None:
    files = sorted((ROOT / "datasets/calibration/cassettes").glob("authored-score-*/*.json"))
    assert files, "Authored cassette inputs are missing"
    for path in files:
        assert fixture_problems(json.loads(path.read_text())) == [], str(path)


def test_readme_calibration_table_contains_only_measured_evidence() -> None:
    table = measurement_table((ROOT / "README.md").read_text())
    assert not re.search(r"synthetic|authored|replay", table, re.IGNORECASE)
    targets = re.findall(r"\]\(([^)]+)\)", table)
    assert targets
    for target in targets:
        assert (ROOT / target).exists(), target


def test_provider_identity_and_invented_usage_are_rejected() -> None:
    assert fixture_problems({"model": "provider/model", "usage": None})
    assert fixture_problems({"model": "authored-fixture", "usage": {"total_tokens": 230}})
    assert fixture_problems({"model": "authored-fixture", "usage": None}) == []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    assert fixture_problems({"model": "authored-fixture", "usage": usage}) == []



def test_missing_measurement_heading_fails_loudly() -> None:
    with pytest.raises(ValueError, match="heading is missing"):
        measurement_table("# Other content")
