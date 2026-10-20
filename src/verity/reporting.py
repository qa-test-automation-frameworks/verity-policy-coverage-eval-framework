"""Per-run token and cost summary for CI job output.

render_cost_summary(accumulator) -> str
    Returns a markdown table of per-label calls/tokens/cost plus totals.

write_step_summary(text)
    Appends text to $GITHUB_STEP_SUMMARY when running in CI, otherwise
    writes to reports/cost-summary-local.md.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


def build_usage_report(
    accumulator: RunAccumulator,
    outcomes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe, prompt-free request ledger and per-test rollups."""
    by_test: dict[str, dict[str, Any]] = {}
    by_model_label: dict[str, dict[str, Any]] = {}

    def empty_stats() -> dict[str, Any]:
        return {
            "requests": 0,
            "succeeded": 0,
            "failed": 0,
            "incomplete": 0,
            "usage_missing": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "priced_requests": 0,
            "unpriced_requests": 0,
        }

    def add_event(stats: dict[str, Any], event: Any) -> None:
        stats["requests"] += 1
        if event.status == "succeeded":
            stats["succeeded"] += 1
            usage = event.usage
            if event.usage_reported and usage is not None:
                stats["prompt_tokens"] += usage.prompt_tokens
                stats["completion_tokens"] += usage.completion_tokens
                stats["total_tokens"] += usage.total_tokens
            else:
                stats["usage_missing"] += 1
            if event.estimated_cost_usd is not None:
                stats["estimated_cost_usd"] += event.estimated_cost_usd
            if event.cost_priced is True:
                stats["priced_requests"] += 1
            elif event.cost_priced is False:
                stats["unpriced_requests"] += 1
        elif event.status == "failed":
            stats["failed"] += 1
        else:
            stats["incomplete"] += 1

    for test_id, outcome in (outcomes or {}).items():
        stats = empty_stats()
        stats["outcome"] = outcome
        stats["sut"] = empty_stats()
        stats["judge"] = empty_stats()
        by_test[test_id] = stats

    request_rows = []
    for event in accumulator.requests:
        test_id = event.test_id or "<unattributed>"
        stats = by_test.setdefault(test_id, empty_stats())
        add_event(stats, event)
        role = "judge" if event.label == "judge" else "sut"
        role_stats = stats.setdefault(role, empty_stats())
        add_event(role_stats, event)

        model_label = f"{event.model} | {event.label or 'unlabeled'}"
        model_stats = by_model_label.setdefault(model_label, empty_stats())
        add_event(model_stats, event)
        row = asdict(event)
        request_rows.append(row)

    suite = empty_stats()
    for event in accumulator.requests:
        add_event(suite, event)
    suite["models"] = sorted({event.model for event in accumulator.requests})

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "privacy": {
            "request_and_response_bodies_included": False,
            "credentials_or_headers_included": False,
            "count_scope": (
                "One row per LLMProvider completion submission or cassette replay. "
                "LiteLLM-internal transport retries are not individually exposed."
            ),
        },
        "suite": suite,
        "by_test": dict(sorted(by_test.items())),
        "by_model_and_label": dict(sorted(by_model_label.items())),
        "requests": request_rows,
    }


def render_usage_summary(report: dict[str, Any], *, include_tests: bool = True) -> str:
    """Render a compact per-test and suite token/request report for logs and CI."""

    def cost_display(stats: dict[str, Any]) -> str:
        succeeded = stats["succeeded"]
        unknown = stats["unpriced_requests"] + stats["usage_missing"]
        if succeeded == 0:
            return "not available"
        if unknown == succeeded:
            return "unpriced/unavailable"
        cost = f"${stats['estimated_cost_usd']:.6f}"
        return f"partial {cost}; {unknown} unavailable" if unknown else cost

    suite = report["suite"]
    lines = [
        "## LLM API Request & Token Usage",
        "",
        (
            f"Suite: **{suite['requests']} requests** "
            f"({suite['succeeded']} succeeded, {suite['failed']} failed, "
            f"{suite['incomplete']} incomplete); **{suite['total_tokens']:,} tokens** "
            f"(prompt {suite['prompt_tokens']:,}, completion {suite['completion_tokens']:,}); "
            f"estimated cost {cost_display(suite)}."
        ),
        f"Usage unavailable for {suite['usage_missing']} successful request(s); "
        f"{suite['unpriced_requests']} request(s) used models without a verified price.",
        (
            "Token totals use provider-reported usage from successful requests; "
            "failures may have no usage metadata."
        ),
        "Estimated cost covers successful calls with reported usage; it is not billing data.",
        "",
    ]
    if include_tests and report["by_test"]:
        lines.extend(
            [
                (
                    "| Test | Outcome | Requests (SUT/judge) | SUT tok | Judge tok | "
                    "Total tok | Est. cost |"
                ),
                "|------|---------|-----------------------:|--------:|----------:|----------:|----------------:|",
            ]
        )
        for test_id, stats in report["by_test"].items():
            empty_role_stats = {"requests": 0, "total_tokens": 0}
            sut_stats = stats.get("sut", empty_role_stats)
            judge_stats = stats.get("judge", empty_role_stats)
            safe_test_id = test_id.replace("|", "\\|").replace("`", "'")
            lines.append(
                f"| `{safe_test_id}` | {stats.get('outcome', 'n/a')} | "
                f"{sut_stats['requests']} / {judge_stats['requests']} | "
                f"{sut_stats['total_tokens']:,} | {judge_stats['total_tokens']:,} | "
                f"{stats['total_tokens']:,} | {cost_display(stats)} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def render_request_ledger(report: dict[str, Any]) -> str:
    """Render individual request metadata without prompt/response contents."""
    lines = ["Individual request events (sanitized):"]
    for event in report["requests"]:
        usage = event["usage"] or {}
        test_id = (event["test_id"] or "<unattributed>").replace("\n", " ")
        lines.append(
            f"{event['request_id']} test={test_id} label={event['label'] or 'unlabeled'} "
            f"model={event['model']} source={event['source']} status={event['status']} "
            f"latency_ms={event['latency_ms']} tokens="
            f"{usage.get('prompt_tokens', 0)}/{usage.get('completion_tokens', 0)}/"
            f"{usage.get('total_tokens', 0)} error={event['error_type'] or '-'}"
        )
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
