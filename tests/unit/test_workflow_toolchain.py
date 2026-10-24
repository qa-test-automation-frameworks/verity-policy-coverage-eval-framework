"""Keep evidence producer scheduling and the uv version contract explicit."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _producer_contract(workflow: dict) -> None:
    triggers = workflow["on"]
    assert "workflow_dispatch" in triggers
    assert triggers["schedule"] == [{"cron": "23 5 * * *"}]
    assert workflow["concurrency"]["cancel-in-progress"] == (
        "${{ github.event_name == 'pull_request' }}"
    )
    assert workflow["jobs"]["lint-type-test"]["strategy"]["matrix"]["python-version"] == [
        "3.12.15",
        "3.13.16",
    ]


def test_daily_producer_contract() -> None:
    workflow = yaml.load(
        (ROOT / ".github/workflows/pr-gate.yml").read_text(), Loader=yaml.BaseLoader
    )
    _producer_contract(workflow)


@pytest.mark.parametrize("trigger", ["schedule", "workflow_dispatch"])
def test_daily_producer_rejects_a_missing_trigger(trigger: str) -> None:
    workflow = yaml.load(
        (ROOT / ".github/workflows/pr-gate.yml").read_text(), Loader=yaml.BaseLoader
    )
    del workflow["on"][trigger]
    with pytest.raises((AssertionError, KeyError)):
        _producer_contract(workflow)


def test_every_uv_action_reads_the_project_pin() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        pin = tomllib.load(handle)["tool"]["uv"]["required-version"]
    assert pin == "==0.13.0"
    assert "ghcr.io/astral-sh/uv:0.13.0@sha256:" in (ROOT / "Dockerfile").read_text()
    found = 0
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                if step.get("uses", "").startswith("astral-sh/setup-uv@"):
                    assert "with" not in step or isinstance(step["with"], dict), str(path)
                    assert "version" not in step.get("with", {}), str(path)
                    found += 1
    assert found > 0
