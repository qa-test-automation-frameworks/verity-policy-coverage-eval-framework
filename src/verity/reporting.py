"""Per-run token and cost summary for CI job output.

render_cost_summary(accumulator) -> str
    Returns a markdown table of per-label calls/tokens/cost plus totals.

write_step_summary(text)
    Appends text to $GITHUB_STEP_SUMMARY when running in CI, otherwise
    writes to reports/cost-summary-local.md.
"""

from __future__ import annotations

import os
from pathlib import Path

from verity.cost import RunAccumulator


def render_cost_summary(accumulator: RunAccumulator) -> str:
    """Return a markdown cost summary table for a completed run."""
    records = accumulator.records
    if not records:
        return "_No LLM calls recorded._\n"

    from collections import defaultdict

    label_stats: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"calls": 0, "prompt": 0, "completion": 0, "total": 0, "cost": 0.0, "unpriced": 0}
    )
    for r in records:
        s = label_stats[r.label or "unlabeled"]
        s["calls"] = int(s["calls"]) + 1
        s["prompt"] = int(s["prompt"]) + r.usage.prompt_tokens
        s["completion"] = int(s["completion"]) + r.usage.completion_tokens
        s["total"] = int(s["total"]) + r.usage.total_tokens
        s["cost"] = float(s["cost"]) + r.cost.total_usd
        if not r.cost.priced:
            s["unpriced"] = int(s["unpriced"]) + 1

    grand_calls = sum(int(s["calls"]) for s in label_stats.values())
    grand_prompt = sum(int(s["prompt"]) for s in label_stats.values())
    grand_completion = sum(int(s["completion"]) for s in label_stats.values())
    grand_total = sum(int(s["total"]) for s in label_stats.values())
    grand_cost = sum(float(s["cost"]) for s in label_stats.values())
    grand_unpriced = sum(int(s["unpriced"]) for s in label_stats.values())

    def _render_cost(s: dict[str, float | int]) -> str:
        calls = int(s["calls"])
        unpriced = int(s["unpriced"])
        if unpriced == calls:
            return "unpriced"
        if unpriced:
            return f"${float(s['cost']):.6f} ({unpriced}/{calls} calls unpriced)"
        return f"${float(s['cost']):.6f}"

    lines: list[str] = [
        "## Token & Cost Summary",
        "",
        "| Label | Calls | Prompt tok | Completion tok | Total tok | Cost (USD) |",
        "|-------|------:|-----------:|---------------:|----------:|-----------:|",
    ]
    for label, s in sorted(label_stats.items()):
        lines.append(
            f"| `{label}` | {int(s['calls'])} | {int(s['prompt']):,} | "
            f"{int(s['completion']):,} | {int(s['total']):,} | "
            f"{_render_cost(s)} |"
        )
    if grand_unpriced == grand_calls and grand_calls > 0:
        total_cost_cell = "unpriced"
    elif grand_unpriced:
        total_cost_cell = f"${grand_cost:.6f} ({grand_unpriced}/{grand_calls} calls unpriced)"
    else:
        total_cost_cell = f"${grand_cost:.6f}"
    lines += [
        f"| **Total** | **{grand_calls}** | **{grand_prompt:,}** | "
        f"**{grand_completion:,}** | **{grand_total:,}** | **{total_cost_cell}** |",
        "",
    ]
    return "\n".join(lines) + "\n"


_local_summary_written_this_process: set[Path] = set()


def write_step_summary(text: str) -> None:
    """Write text to $GITHUB_STEP_SUMMARY or reports/cost-summary-local.md.

    The local file is truncated on the first write of each process (so
    scratch evidence from a previous run doesn't accumulate unbounded across
    many local invocations) and appended to on subsequent writes within the
    same process, so multiple summaries produced by one run still land in
    the same file.
    """
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as fh:
            fh.write(text)
    else:
        out = Path("reports/cost-summary-local.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        resolved = out.resolve()
        mode = "a" if resolved in _local_summary_written_this_process else "w"
        with out.open(mode) as fh:
            fh.write(text)
        _local_summary_written_this_process.add(resolved)
