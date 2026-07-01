"""Trace demo: runs one agent.answer() call with tracing enabled.

Uses the hermetic cassette replay path — no API key required.
Spans are exported to reports/traces/spans-<timestamp>.jsonl.

Usage:
    make trace-demo
    # or directly:
    VERITY_TRACING=1 PYTHONPATH=src uv run python scripts/trace_demo.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Enable tracing before importing verity.tracing
os.environ.setdefault("VERITY_TRACING", "1")
os.environ.setdefault("VERITY_TRACE_EXPORTER", "file")

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import warnings  # noqa: E402

from sut.agent import CoverageAgent  # noqa: E402
from sut.retriever import FixtureRetriever  # noqa: E402
from verity.cassettes import CassetteLibrary  # noqa: E402
from verity.config import Provider, Settings  # noqa: E402
from verity.cost import RunAccumulator  # noqa: E402
from verity.providers import LLMProvider  # noqa: E402
from verity.reporting import render_cost_summary  # noqa: E402
from verity.tracing import init_tracing  # noqa: E402

_CASSETTE_DIR = Path("datasets/cassettes")
_FIXTURE_ID = "defect-7-prompt-injection"
_QUERY = "What does my policy cover overall?"
_MEMBER_ID = "MBR-001"


def main() -> None:
    init_tracing("verity-trace-demo")

    # Isolated from any local .env and pinned to the provider/model the
    # committed cassette was recorded against, so this stays hermetic
    # regardless of what a developer has configured for live runs.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        settings = Settings(
            _env_file=None,
            provider=Provider.zai,
            model="glm-4.5",
            cassette_mode="replay",
            cassette_dir=_CASSETTE_DIR,
        )

    lib = CassetteLibrary(_CASSETTE_DIR)
    accumulator = RunAccumulator()
    provider = LLMProvider(settings, accumulator, cassette_library=lib)
    retriever = FixtureRetriever(_FIXTURE_ID)
    agent = CoverageAgent(settings=settings, retriever=retriever, provider=provider)

    print(f"Running agent for: {_QUERY!r}")
    response = agent.answer(_QUERY, member_id=_MEMBER_ID)
    print(f"Answer ({len(response.answer)} chars): {response.answer[:120]}...")
    print()
    print(render_cost_summary(accumulator))
    print("Trace spans written to reports/traces/")


if __name__ == "__main__":
    main()
