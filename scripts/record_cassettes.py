"""Cassette recording / authoring script.

Two modes:

  --live    Record real model responses (requires API key in .env).
            Runs CoverageAgent against every golden case using the configured
            provider and writes hash-keyed cassette JSON files.

  --author  (default) Inject hand-authored responses from
            datasets/cassettes/authored/<case_id>.yaml and write cassette
            files keyed by the request hash that the agent would compute.
            No API key required.  Used to bootstrap Tier-1 replay.

Usage:
  uv run python scripts/record_cassettes.py [--live | --author] [--case CASE_ID]
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Any

# Ensure src is on the path when run directly
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import yaml  # noqa: E402

from sut.agent import CoverageAgent, _build_system_prompt, _load_members  # noqa: E402
from sut.retriever import FixtureRetriever  # noqa: E402
from sut.tools.coverage_calculator import COVERAGE_CALCULATOR_SCHEMA  # noqa: E402
from verity.cassettes import (  # noqa: E402
    CassetteLibrary,
    CassettePayload,
    ReplayFunction,
    ReplayToolCall,
    request_key,
)
from verity.config import Provider, Settings  # noqa: E402
from verity.golden import GoldenCase, load_golden  # noqa: E402

_AUTHORED_DIR = Path("datasets/cassettes/authored")
_CASSETTE_DIR = Path("datasets/cassettes")
_GOLDEN_DIR = Path("datasets/golden")


def _settings_no_key() -> Settings:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Settings(cassette_mode="record", cassette_dir=_CASSETTE_DIR)


def _compute_first_turn_key(
    case: GoldenCase,
    litellm_model: str,
    temp: float,
    max_tok: int,
) -> str:
    """Compute the cassette key for the agent's first LLM call for a given case."""
    members = _load_members()
    member = members.get(case.member_id, next(iter(members.values())))
    retriever = FixtureRetriever(case.id)
    chunks = retriever.retrieve(case.query)
    system_prompt = _build_system_prompt(member, chunks)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": case.query},
    ]
    # The agent always passes the tool schema to the first LLM call regardless of behavior.
    tools: list[dict[str, Any]] = [COVERAGE_CALCULATOR_SCHEMA]
    return request_key(litellm_model, messages, tools, temp, max_tok)


def _compute_second_turn_key(
    case: GoldenCase,
    first_payload: CassettePayload,
    litellm_model: str,
    temp: float,
    max_tok: int,
) -> str | None:
    """Compute the cassette key for the agent's second turn (tool result → final answer)."""
    if not first_payload.tool_calls:
        return None

    members = _load_members()
    member = members.get(case.member_id, next(iter(members.values())))
    retriever = FixtureRetriever(case.id)
    chunks = retriever.retrieve(case.query)
    system_prompt = _build_system_prompt(member, chunks)

    # Reproduce the exact message sequence the agent builds for the second turn
    assistant_tool_calls: list[dict[str, Any]] = [
        {
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
        }
        for tc in first_payload.tool_calls
    ]
    tool_result_msgs: list[dict[str, Any]] = []
    for tc in first_payload.tool_calls:
        try:
            from sut.tools.coverage_calculator import run_coverage_calculator

            args: dict[str, Any] = json.loads(tc.function.arguments)
            result: dict[str, Any] = run_coverage_calculator(args)
        except Exception:
            result = {"error": "tool error"}
        tool_result_msgs.append(
            {
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result),
            }
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": case.query},
        {"role": "assistant", "content": first_payload.content, "tool_calls": assistant_tool_calls},
        *tool_result_msgs,
    ]
    return request_key(litellm_model, messages, None, temp, max_tok)


def _load_authored(case_id: str) -> list[dict[str, Any]]:
    path = _AUTHORED_DIR / f"{case_id}.yaml"
    if not path.exists():
        return []
    raw: Any = yaml.safe_load(path.read_text())
    if isinstance(raw, dict):
        return raw.get("turns", [])
    return []


def _authored_to_payload(turn: dict[str, Any], model: str) -> CassettePayload:
    raw_tcs: list[dict[str, Any]] = turn.get("tool_calls", [])
    tcs = [
        ReplayToolCall(
            id=tc["id"],
            function=ReplayFunction(
                name=tc["function"]["name"], arguments=tc["function"]["arguments"]
            ),
        )
        for tc in raw_tcs
    ]
    return CassettePayload(
        content=turn.get("content", ""),
        tool_calls=tcs,
        prompt_tokens=turn.get("prompt_tokens", 50),
        completion_tokens=turn.get("completion_tokens", 100),
        total_tokens=turn.get("prompt_tokens", 50) + turn.get("completion_tokens", 100),
        model=model,
    )


def run_author_mode(cases: list[GoldenCase]) -> None:
    """Write cassettes from hand-authored YAML files (no API calls).

    Pinned to zai/glm-4.5, isolated from any local .env: authored cassettes
    must be keyed identically to the already-committed ones regardless of
    what a developer has configured for live runs.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        settings = Settings(
            _env_file=None, provider=Provider.zai, model="glm-4.5", cassette_dir=_CASSETTE_DIR
        )
    litellm_model, _, _ = settings.resolved_provider()
    temp = settings.temperature
    max_tok = settings.max_tokens
    lib = CassetteLibrary(_CASSETTE_DIR)

    ok = 0
    skipped = 0
    for case in cases:
        turns = _load_authored(case.id)
        if not turns:
            print(
                f"  SKIP  {case.id!r} — no authored file at {_AUTHORED_DIR / (case.id + '.yaml')}"
            )
            skipped += 1
            continue

        first_payload = _authored_to_payload(turns[0], litellm_model)
        first_key = _compute_first_turn_key(case, litellm_model, temp, max_tok)
        lib.save(first_key, first_payload, request_preview=f"[turn-1] {case.query[:80]}")

        if len(turns) > 1 and first_payload.tool_calls:
            second_key = _compute_second_turn_key(case, first_payload, litellm_model, temp, max_tok)
            if second_key:
                second_payload = _authored_to_payload(turns[1], litellm_model)
                lib.save(second_key, second_payload, request_preview=f"[turn-2] {case.query[:80]}")

        print(f"  WROTE {case.id!r} → {first_key[:12]}…")
        ok += 1

    print(f"\nDone: {ok} written, {skipped} skipped (no authored YAML).")


def run_live_mode(cases: list[GoldenCase]) -> None:
    """Record real model responses (requires API key)."""
    settings = _settings_no_key()

    for case in cases:
        print(f"  Recording {case.id!r}…")
        retriever = FixtureRetriever(case.id)
        agent = CoverageAgent(settings=settings, retriever=retriever)
        try:
            agent.answer(case.query, member_id=case.member_id)
            print(f"  DONE  {case.id!r}")
        except Exception as exc:
            print(f"  ERROR {case.id!r}: {exc}", file=sys.stderr)

    count = len(list(_CASSETTE_DIR.glob("*.json")))
    print(f"\nDone. {count} cassette files in {_CASSETTE_DIR}/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="Record from live model")
    mode.add_argument("--author", action="store_true", default=True, help="Use authored YAMLs")
    parser.add_argument("--case", help="Record only this case ID")
    args = parser.parse_args()

    cases = load_golden(_GOLDEN_DIR)
    if args.case:
        cases = [c for c in cases if c.id == args.case]
        if not cases:
            print(f"No case found with id={args.case!r}", file=sys.stderr)
            sys.exit(1)

    if args.live:
        run_live_mode(cases)
    else:
        run_author_mode(cases)


if __name__ == "__main__":
    main()
