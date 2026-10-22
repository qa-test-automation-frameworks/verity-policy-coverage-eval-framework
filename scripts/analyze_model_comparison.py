"""Analyze paired correctness and cost records without contacting a provider."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from verity.paired_comparison import analyze_paired_comparison


def _read_jsonl(path: Path, side: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            diagnostics.append(
                {
                    "code": "invalid_json",
                    "message": f"line {line_number}: {exc.msg}",
                    "side": side,
                    "case_id": "",
                }
            )
            continue
        if not isinstance(record, dict):
            diagnostics.append(
                {
                    "code": "invalid_record",
                    "message": f"line {line_number} must contain a JSON object",
                    "side": side,
                    "case_id": "",
                }
            )
            continue
        records.append(record)
    return records, diagnostics


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _percent(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.1%}"


def render_markdown(report: dict[str, Any]) -> str:
    identities = report["identities"]
    quality = report["quality"]
    cost = report["cost"]
    latency = report["latency"]
    baseline = identities["baseline"]
    challenger = identities["challenger"]
    interval = quality["bootstrap_95_percentile_interval"]
    interval_text = (
        "unknown" if interval is None else f"[{interval[0]:+.3f}, {interval[1]:+.3f}]"
    )
    denominators = report["denominators"]
    cost_delta = cost["challenger_minus_baseline_mean_usd"]
    cost_delta_text = "unknown" if cost_delta is None else f"{cost_delta:.6f}"
    latency_delta = latency["challenger_minus_baseline_mean_ms"]
    latency_delta_text = "unknown" if latency_delta is None else f"{latency_delta:.1f}"
    lines = [
        "# Paired model comparison",
        "",
        f"**Decision: {report['decision']}** — {report['decision_reason']}",
        "",
        f"Source kind: `{report['source_kind']}`  ",
        f"Evidence scope: `{report['evidence_scope']}`  ",
        f"Cohort: `{identities['cohort_hash'] or 'inconsistent'}`  ",
        f"Baseline: `{', '.join(baseline['candidate_ids']) or 'unknown'}`; config "
        f"`{', '.join(baseline['config_ids']) or 'unknown'}`; source "
        f"`{', '.join(baseline['source_ids']) or 'unknown'}`  ",
        f"Challenger: `{', '.join(challenger['candidate_ids']) or 'unknown'}`; config "
        f"`{', '.join(challenger['config_ids']) or 'unknown'}`; source "
        f"`{', '.join(challenger['source_ids']) or 'unknown'}`",
        "",
        "| Evidence | Result |",
        "|---|---:|",
        f"| Independent valid pairs | {denominators['valid_correctness_pairs']} / "
        f"{denominators['common_case_ids']} |",
        f"| Success rate, baseline / challenger | "
        f"{_percent(quality['baseline_success_rate'])} / "
        f"{_percent(quality['challenger_success_rate'])} |",
        f"| Wins / ties / losses | {quality['wins']} / {quality['ties']} / {quality['losses']} |",
        f"| Paired mean correctness delta | {_percent(quality['paired_mean_delta'])} |",
        f"| Paired bootstrap 95% interval | `{interval_text}` |",
        f"| Cost delta, challenger - baseline | {cost_delta_text} USD "
        f"({cost['paired_cost_count']}/{cost['paired_cost_denominator']} pairs) |",
        f"| Cost savings supported | {cost['cost_saving_supported']} — "
        f"{cost['reason']} |",
        f"| Latency delta, challenger - baseline | {latency_delta_text} ms "
        f"({latency['paired_latency_count']}/{latency['paired_latency_denominator']} pairs) |",
        f"| Mean input tokens, baseline / challenger | "
        f"{report['tokens']['baseline_mean_input_tokens']} / "
        f"{report['tokens']['challenger_mean_input_tokens']} "
        f"({report['tokens']['input_token_pairs']}/{report['tokens']['pair_denominator']} pairs) |",
        f"| Mean output tokens, baseline / challenger | "
        f"{report['tokens']['baseline_mean_output_tokens']} / "
        f"{report['tokens']['challenger_mean_output_tokens']} "
        f"({report['tokens']['output_token_pairs']}/"
        f"{report['tokens']['pair_denominator']} pairs) |",
        "",
        "Input and oracle hashes are listed per case in the JSON output. "
        "The analyzer pairs by `case_id`, "
        "then requires identical input, oracle, cohort, and source-kind identities; "
        "it does not silently inner-join.",
        "",
        "## Decision policy",
        "",
        "Critical challenger failure rejects first. Otherwise invalid or incomplete pairs, "
        "or fewer than 30 independent valid cases, are inconclusive. With adequate data, "
        "the paired case bootstrap uses 2,000 resamples and seed 20261021: the baseline "
        "wins if the upper bound is below -0.02, the result is inconclusive if the interval "
        "crosses -0.02, and the candidate wins the quality-only policy if the lower bound "
        "is at least -0.02. This does not deploy anything automatically.",
        "",
    ]
    if report["diagnostics"]:
        lines += ["## Exclusions and input problems", ""]
        lines.extend(
            f"- `{item['code']}` ({item['side'] or 'input'}): {item['message']}"
            for item in report["diagnostics"]
        )
        lines.append("")
    lines += [
        "<details>",
        "<summary>Per-case input and oracle identities</summary>",
        "",
        "| Case | Baseline input | Challenger input | Baseline oracle | Challenger oracle |",
        "|---|---|---|---|---|",
    ]
    lines.extend(
        f"| `{row['case_id']}` | `{row['baseline_input_hash']}` | "
        f"`{row['challenger_input_hash']}` | `{row['baseline_oracle_version']}` | "
        f"`{row['challenger_oracle_version']}` |"
        for row in report["case_outcomes"]
    )
    lines += ["", "</details>", ""]
    input_files = report.get("input_files", {})
    if input_files:
        lines += ["## Input files", ""]
        lines.extend(
            f"- {side}: `{details['path']}` SHA-256 `{details['sha256']}`"
            for side, details in sorted(input_files.items())
        )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--challenger", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="one-page Markdown report")
    parser.add_argument("--json-out", type=Path, help="JSON report (defaults beside --out)")
    args = parser.parse_args()

    baseline, baseline_errors = _read_jsonl(args.baseline, "baseline")
    challenger, challenger_errors = _read_jsonl(args.challenger, "challenger")
    report = analyze_paired_comparison(
        baseline,
        challenger,
        parse_diagnostics=[*baseline_errors, *challenger_errors],
    )
    report["input_files"] = {
        "baseline": {"path": args.baseline.as_posix(), "sha256": _sha256(args.baseline)},
        "challenger": {"path": args.challenger.as_posix(), "sha256": _sha256(args.challenger)},
    }

    markdown_path = args.out
    json_path = args.json_out or args.out.with_suffix(".json")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Decision: {report['decision']}; wrote {markdown_path} and {json_path}")
    for item in report["diagnostics"]:
        print(f"{item['code']} ({item['side']}): {item['message']}")
    return 0 if report["input_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
