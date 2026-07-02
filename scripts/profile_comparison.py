"""Structural comparison of the seeded vs. clean SUT profiles across the golden set.

Makes no live model calls: it builds the system prompt CoverageAgent would send
for each golden case under both profiles (using the same retrieval fixtures
Tier-1 replays against) and reports the concrete, code-level differences
between them, so the "clean vs. seeded" split is demonstrated on the actual
dataset rather than asserted in prose.

Usage:
  uv run python scripts/profile_comparison.py [--out PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sut.agent import _build_system_prompt, _load_members  # noqa: E402
from sut.retriever import FixtureRetriever  # noqa: E402
from verity.golden import GoldenCase, load_golden  # noqa: E402

_GOLDEN_DIR = Path("datasets/golden")
_DEFAULT_OUT_PATH = Path("docs/profile-comparison.md")


def _compare_case(case: GoldenCase, members: dict[str, dict[str, object]]) -> dict[str, object]:
    member = members[case.member_id]
    chunks = FixtureRetriever(case.id).retrieve(case.query)
    seeded_prompt = _build_system_prompt(member, chunks, clean=False)
    clean_prompt = _build_system_prompt(member, chunks, clean=True)
    member_name = str(member["name"])
    return {
        "id": case.id,
        "pii_in_seeded": member_name in seeded_prompt,
        "pii_in_clean": member_name in clean_prompt,
        "tool_guidance_in_clean": "do not swap these" in clean_prompt.lower(),
        "tool_guidance_in_seeded": "do not swap these" in seeded_prompt.lower(),
    }


def render_report(rows: list[dict[str, object]]) -> str:
    lines = [
        "# Seeded vs. Clean SUT Profile Comparison",
        "",
        "Structural comparison of the two `sut_profile` settings across every "
        "golden case, built without any live model call.",
        "",
        "## Unconditional differences (not case-dependent)",
        "",
        "| Behavior | seeded | clean |",
        "|---|---|---|",
        "| Member name/DOB logged at DEBUG (`guardrails.log_member_context`) "
        "| full dict logged | only `member_id` logged |",
        "| Structurally invalid conversation "
        "(`verity.conversation.validate_conversation` fails) "
        "| logged as a warning, request proceeds | returned as a "
        "`invalid_conversation_structure` safe-failure |",
        "",
        "## Per-case system prompt differences",
        "",
        "| Case | Member PII in prompt (seeded) | Member PII in prompt (clean) "
        "| Tool-arg disambiguation guidance (clean) |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['id']}` | {'yes' if row['pii_in_seeded'] else 'no'} "
            f"| {'yes' if row['pii_in_clean'] else 'no'} "
            f"| {'yes' if row['tool_guidance_in_clean'] else 'no'} |"
        )
    n = len(rows)
    pii_seeded_count = sum(1 for r in rows if r["pii_in_seeded"])
    pii_clean_count = sum(1 for r in rows if r["pii_in_clean"])
    lines += [
        "",
        f"**Summary:** {pii_seeded_count}/{n} cases carry member PII in the "
        f"seeded prompt; {pii_clean_count}/{n} carry it in the clean prompt.",
        "",
        "_Regenerate: `make profile-comparison`._",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(_DEFAULT_OUT_PATH), help="Report output path")
    args = parser.parse_args()

    cases = load_golden(_GOLDEN_DIR)
    members = _load_members()
    rows = [_compare_case(case, members) for case in cases if case.member_id in members]

    report = render_report(rows)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
