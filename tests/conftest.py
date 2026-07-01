"""Session-wide environment isolation for the hermetic test tiers.

DeepEval's pytest plugin (registered via the `pytest11` entry point) calls
`autoload_dotenv()` at import time, which loads .env into the real process
environment before any test collection happens. That means any VERITY_*
value a developer has configured locally for live runs becomes visible to
`os.environ` for the entire pytest session, which defeats per-call
`Settings(_env_file=None, ...)` isolation — real environment variables take
priority over an unset dotenv file regardless of that flag.

The hermetic tiers (unit, deterministic, adversarial) must produce the same
result on every machine, independent of what a developer has configured
locally for live runs. This fixture purges the ambient VERITY_* / legacy
provider env vars for those tiers only, so their results depend solely on
explicit fixture/test configuration rather than the local environment.
Tests under tests/semantic and tests/live are left untouched — they are
supposed to read the live, ambient configuration.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest

_HERMETIC_DIRS = ("tests/unit/", "tests/deterministic/", "tests/adversarial/")

_LEGACY_KEYS_TO_PURGE = (
    "ZAI_API_KEY",
    "OPENROUTER_API_KEY",
    "TOGETHER_API_KEY",
    "NVIDIA_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "ZAI_API_BASE",
    "OPENROUTER_API_BASE",
    "TOGETHER_API_BASE",
    "NVIDIA_API_BASE",
    "GOOGLE_API_BASE",
)


def _is_hermetic(nodeid: str) -> bool:
    return any(nodeid.startswith(prefix) for prefix in _HERMETIC_DIRS)


@pytest.fixture(autouse=True)
def _isolate_hermetic_env(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    if not _is_hermetic(request.node.nodeid):
        yield
        return

    for key in list(os.environ):
        if key.startswith("VERITY_") or key in _LEGACY_KEYS_TO_PURGE:
            monkeypatch.delenv(key, raising=False)
    yield
