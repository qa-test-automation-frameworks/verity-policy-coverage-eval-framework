#!/usr/bin/env python3
"""Run a no-key command with provider credentials and dotenv disabled."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping

_PRESERVED_VERITY_SETTINGS = {
    "VERITY_TRACING",
    "VERITY_TRACE_EXPORTER",
    "VERITY_TRACE_OUTPUT_PATH",
}
_API_BASES = {
    "ZAI_API_BASE",
    "OPENROUTER_API_BASE",
    "TOGETHER_API_BASE",
    "NVIDIA_API_BASE",
    "GOOGLE_API_BASE",
    "OPENAI_API_BASE",
    "ANTHROPIC_BASE_URL",
}


def hermetic_environment(source: Mapping[str, str]) -> dict[str, str]:
    """Return an environment with no inherited provider credentials or routing."""
    environment = dict(source)
    for name in tuple(environment):
        upper_name = name.upper()
        is_provider_secret = upper_name.endswith("_API_KEY") or upper_name.endswith("_API_KEY_2")
        is_unpreserved_verity_setting = name.startswith("VERITY_") and name not in (
            _PRESERVED_VERITY_SETTINGS
        )
        if is_provider_secret or upper_name in _API_BASES or is_unpreserved_verity_setting:
            environment.pop(name, None)

    # LiteLLM 1.106.0 supports the local cost map switch; DeepEval supports
    # both dotenv and telemetry controls. Hugging Face's offline flag keeps
    # embedding code on its prepared local cache.
    environment.update(
        {
            "LITELLM_LOCAL_MODEL_COST_MAP": "True",
            "DEEPEVAL_DISABLE_DOTENV": "1",
            "DEEPEVAL_TELEMETRY_OPT_OUT": "true",
            "VERITY_DISABLE_DOTENV": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }
    )
    return environment


def main(argv: list[str] | None = None) -> int:
    command = list(sys.argv[1:] if argv is None else argv)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("Usage: run_hermetic.py -- COMMAND [ARG ...]", file=sys.stderr)
        return 2

    return subprocess.run(command, env=hermetic_environment(os.environ), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
