"""The shared no-key launcher clears ambient credentials before imports."""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run_hermetic.py"


def test_launcher_clears_credentials_and_dotenv_before_child_imports(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("VERITY_PROVIDER=nvidia\nVERITY_ZAI_API_KEY=dotenv-secret\n")
    child = """
import os
import sys
from verity.config import Provider, Settings

assert os.environ.get("VERITY_ZAI_API_KEY") is None
assert os.environ.get("ZAI_API_KEY") is None
assert os.environ.get("OPENAI_API_KEY") is None
assert os.environ.get("VERITY_PROVIDER") is None
assert os.environ.get("VERITY_DISABLE_DOTENV") == "1"
assert os.environ.get("DEEPEVAL_DISABLE_DOTENV") == "1"
assert os.environ.get("DEEPEVAL_TELEMETRY_OPT_OUT") == "true"
assert os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP") == "True"
assert os.environ.get("HF_HUB_OFFLINE") == "1"
assert os.environ.get("VERITY_TRACING") == "1"
assert os.environ.get("VERITY_TRACE_EXPORTER") == "file"
assert "litellm" not in sys.modules
assert "openai" not in sys.modules
settings = Settings()
assert settings.provider is Provider.openrouter
assert settings.zai_api_key is None
"""
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONPATH": str(ROOT / "src"),
            "VERITY_PROVIDER": "nvidia",
            "VERITY_ZAI_API_KEY": "prefixed-secret",
            "ZAI_API_KEY": "legacy-secret",
            "OPENAI_API_KEY": "openai-secret",
            "VERITY_TRACING": "1",
            "VERITY_TRACE_EXPORTER": "file",
            "LITELLM_LOCAL_MODEL_COST_MAP": "False",
        }
    )
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--", sys.executable, "-c", child],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_locked_litellm_import_uses_the_local_cost_map_without_sockets() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked_version = next(
        package["version"] for package in lock["package"] if package["name"] == "litellm"
    )
    child = f"""
import socket
from importlib.metadata import version

attempts = []
def blocked(name):
    def fail(*args, **kwargs):
        attempts.append(name)
        raise AssertionError(f"unexpected network attempt: {{name}}")
    return fail

socket.create_connection = blocked("create_connection")
socket.getaddrinfo = blocked("getaddrinfo")
socket.socket.connect = blocked("connect")
socket.socket.connect_ex = blocked("connect_ex")
assert version("litellm") == {locked_version!r}
import litellm
assert litellm is not None
assert attempts == []
"""
    environment = os.environ.copy()
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--", sys.executable, "-c", child],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
