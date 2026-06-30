"""Promptfoo custom provider: wraps CoverageAgent for red-team evaluation.

Called by promptfoo as a Python provider. Reads the prompt from argv[1] (or
stdin when argv[1] == "-"), runs the agent via hermetic cassette replay or
live (depending on VERITY_CASSETTE_MODE), and returns a promptfoo-compatible
JSON object: {"output": str, "tokenUsage": {...}}.

Usage in redteam.yaml:
  providers:
    - id: "python:promptfoo/provider.py"
      config:
        member_id: MBR-001
"""

from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sut.agent import CoverageAgent  # noqa: E402
from sut.retriever import PolicyRetriever  # noqa: E402
from verity.config import Settings  # noqa: E402
from verity.cost import RunAccumulator  # noqa: E402
from verity.providers import LLMProvider  # noqa: E402


def call_api(prompt: str, options: dict, context: dict) -> dict:
    """Promptfoo provider entry point."""
    member_id: str = (options.get("config") or {}).get("member_id", "MBR-001")
    cassette_mode: str = os.environ.get("VERITY_CASSETTE_MODE", "off")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        settings = Settings(cassette_mode=cassette_mode)

    accumulator = RunAccumulator()
    provider = LLMProvider(settings, accumulator)
    retriever = PolicyRetriever()
    agent = CoverageAgent(settings=settings, retriever=retriever, provider=provider)

    try:
        response = agent.answer(prompt, member_id=member_id)
        output = str(getattr(response, "answer", "") or "")
        tokens = accumulator.total_tokens
        return {
            "output": output,
            "tokenUsage": {
                "total": tokens.total_tokens,
                "prompt": tokens.prompt_tokens,
                "completion": tokens.completion_tokens,
            },
        }
    except Exception as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()
    result = call_api(prompt, {}, {})
    print(json.dumps(result))
