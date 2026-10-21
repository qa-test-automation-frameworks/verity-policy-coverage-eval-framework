"""Cassette replay must stay local until an explicit live call is submitted."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "run_hermetic.py"


def test_replay_hit_and_miss_import_no_provider_sdk_or_open_sockets(tmp_path: Path) -> None:
    child = textwrap.dedent(
        """
        import socket
        import sys
        from pathlib import Path
        from types import ModuleType, SimpleNamespace

        attempts = []

        def blocked(name):
            def fail(*args, **kwargs):
                attempts.append(name)
                raise AssertionError(f"unexpected network attempt: {name}")
            return fail

        socket.create_connection = blocked("create_connection")
        socket.getaddrinfo = blocked("getaddrinfo")
        socket.socket.connect = blocked("connect")
        socket.socket.connect_ex = blocked("connect_ex")

        from verity.cassettes import (
            CassetteLibrary,
            CassetteMissError,
            CassettePayload,
            request_key,
        )
        from verity.config import Provider, Settings
        from verity.cost import RunAccumulator
        from verity.providers import LLMProvider

        assert "litellm" not in sys.modules
        assert "openai" not in sys.modules

        cassette_dir = Path(sys.argv[1]) / "cassettes"
        settings = Settings(
            _env_file=None,
            provider=Provider.zai,
            model="glm-4.5",
            cassette_mode="replay",
            cassette_dir=cassette_dir,
        )
        model, _, _ = settings.resolved_provider()
        messages = [{"role": "user", "content": "replay this"}]
        library = CassetteLibrary(cassette_dir)
        key = request_key(model, messages, None, settings.temperature, settings.max_tokens)
        library.save(
            key,
            CassettePayload(
                content="from cassette",
                tool_calls=[],
                prompt_tokens=2,
                completion_tokens=3,
                total_tokens=5,
                model=model,
            ),
        )
        replay = LLMProvider(settings, cassette_library=library)
        assert replay.complete(messages).content == "from cassette"
        try:
            replay.complete([{"role": "user", "content": "missing cassette"}])
        except CassetteMissError:
            pass
        else:
            raise AssertionError("a cassette miss did not fail fast")
        assert "litellm" not in sys.modules
        assert "openai" not in sys.modules
        assert attempts == []

        # A live route loads the SDK boundary only when it submits a request.
        calls = []
        mocked_litellm = ModuleType("litellm")
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="mocked live response", tool_calls=None)
                )
            ],
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=2, total_tokens=6),
        )

        def completion(**kwargs):
            calls.append(kwargs)
            return response

        mocked_litellm.completion = completion
        sys.modules["litellm"] = mocked_litellm
        live_settings = Settings(
            _env_file=None,
            provider=Provider.zai,
            model="glm-4.5",
            cassette_mode="off",
            cassette_dir=cassette_dir,
        )
        accumulator = RunAccumulator()
        live = LLMProvider(live_settings, accumulator)
        result = live.complete([{"role": "user", "content": "mock this live call"}])
        assert result.content == "mocked live response"
        assert len(calls) == 1
        assert "api_key" not in calls[0]
        assert [event.status for event in accumulator.requests] == ["succeeded"]
        assert len(accumulator.records) == 1
        assert "openai" not in sys.modules
        assert attempts == []
        """
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment["VERITY_ZAI_API_KEY"] = "ambient-secret"
    environment["OPENAI_API_KEY"] = "ambient-openai-secret"
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--", sys.executable, "-c", child, str(tmp_path)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
