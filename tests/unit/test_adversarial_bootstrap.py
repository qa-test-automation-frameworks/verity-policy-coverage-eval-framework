"""Command-level checks for the adversarial CI dependency contract."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).parents[2]
_WORKFLOW_PATH = _ROOT / ".github/workflows/adversarial.yml"
_WORKFLOW = yaml.safe_load(_WORKFLOW_PATH.read_text()) if _WORKFLOW_PATH.is_file() else {}
_PROJECT = tomllib.loads((_ROOT / "pyproject.toml").read_text())
pytestmark = pytest.mark.skipif(
    not _WORKFLOW_PATH.is_file(),
    reason="workflow source is not included in the packaged test image",
)


def _steps(job_name: str) -> dict[str, dict[str, object]]:
    job = _WORKFLOW["jobs"][job_name]
    return {step.get("name", ""): step for step in job["steps"]}


def _selected_extras(command: str) -> set[str]:
    return set(re.findall(r"--extra\s+([A-Za-z0-9_-]+)", command))


def _missing_extras(command: str, required: set[str]) -> set[str]:
    return required - _selected_extras(command)


def test_hermetic_job_installs_locked_test_and_report_extras() -> None:
    extras = _PROJECT["project"]["optional-dependencies"]
    assert {"pytest", "hypothesis"}.issubset(
        {dependency.split(">", maxsplit=1)[0].lower() for dependency in extras["dev"]}
    )
    assert "allure-pytest" in {
        dependency.split(">", maxsplit=1)[0].lower() for dependency in extras["report"]
    }

    steps = _steps("redteam-hermetic")
    assert "needs" not in _WORKFLOW["jobs"]["redteam-hermetic"]
    install = str(steps["Install dependencies"]["run"])
    assert not _missing_extras(install, {"dev", "report"})
    assert "uv sync --frozen" in install

    suite = str(steps["Hermetic adversarial suite"]["run"])
    assert "uv run --no-sync pytest tests/adversarial/ -m adversarial" in suite
    assert "--junitxml reports/junit/adversarial.xml" in suite
    assert "--alluredir reports/allure-results/adversarial" in suite
    provider_environment = {
        "VERITY_ZAI_API_KEY",
        "VERITY_OPENROUTER_API_KEY",
        "VERITY_OPENROUTER_API_KEY_2",
        "VERITY_TOGETHER_API_KEY",
        "VERITY_NVIDIA_API_KEY",
        "VERITY_GOOGLE_API_KEY",
        "ZAI_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENROUTER_API_KEY_2",
        "TOGETHER_API_KEY",
        "NVIDIA_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
    }
    assert all(f"-u {name}" in suite for name in provider_environment)

    verify = str(steps["Verify adversarial reports"]["run"])
    assert "test -s reports/junit/adversarial.xml" in verify
    assert "adversarial_cases" in verify
    assert "*-result.json" in verify

    upload = steps["Upload adversarial reports"]
    assert upload["if"] == "always()"
    uploaded_paths = str(upload["with"]["path"])
    for artifact_path in (
        "reports/junit/adversarial.xml",
        "reports/allure-results/adversarial/",
        "reports/security/summary-local.json",
    ):
        assert artifact_path in uploaded_paths


def test_base_only_install_is_a_dependency_negative_control() -> None:
    required = {"dev", "report"}
    assert _missing_extras("uv sync --frozen", required) == required
    assert not _missing_extras("uv sync --frozen --extra dev --extra report", required)


def test_live_entrypoints_keep_the_base_dependency_set() -> None:
    for job_name in ("redteam-live", "calibrate-live"):
        steps = _steps(job_name)
        install = str(steps["Install dependencies"]["run"])
        assert install == "uv sync --frozen"
        assert "inputs.run_live" in _WORKFLOW["jobs"][job_name]["if"]

    redteam = str(_steps("redteam-live")["Promptfoo live red-team eval"]["run"])
    calibration = str(_steps("calibrate-live")["Live calibration run"]["run"])
    assert "uv run --no-sync npx" in redteam
    assert "uv run --no-sync python scripts/run_calibration.py" in calibration
