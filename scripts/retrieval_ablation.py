"""Retrieval parameter ablation: measures how source_precision and pass-rate
across datasets/retrieval/benchmarks.yaml move as each hand-tuned retrieval
constant is varied, holding the others at their current default.

Runs against the real PolicyRetriever (local ONNX embeddings, no network
after the model is cached, no live LLM API calls) — hermetic in the sense
this repo uses the term elsewhere, but requires the ONNX model cache
(see CONTRIBUTING.md) and skips with a clear message if it's unavailable.

Usage:
  uv run python scripts/retrieval_ablation.py [--out PATH] [--json-out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from verity.config import RetrievalConfig  # noqa: E402
from verity.retrieval_eval import (  # noqa: E402
    RetrievalBenchmark,
    load_retrieval_benchmarks,
    score_retrieval,
)

_DEFAULT_OUT_PATH = Path("docs/retrieval-ablation.md")
_DEFAULT_JSON_PATH = Path("reports/retrieval-ablation/retrieval-ablation.json")

# Sweep points for each parameter, chosen to bracket the current default
# (marked with *) from both directions.
_LEXICAL_WEIGHT_SWEEP = [0.0, 0.25, 0.5, 0.75, 1.0]  # default 0.5
_DISTANCE_MARGIN_SWEEP = [0.10, 0.15, 0.20, 0.30, 0.40]  # default 0.20
_MAX_RELEVANT_DISTANCE_SWEEP = [0.35, 0.40, 0.45, 0.50, 0.55]  # default 0.45


def _run_benchmarks_with_override(
    retriever: Any, benchmarks: list[RetrievalBenchmark], attr: str, value: float
) -> dict[str, float]:
    """Run every benchmark with sut.retriever.<attr> monkeypatched to value.

    Returns {"pass_rate": ..., "mean_source_precision": ...}. Restores the
    original module attribute afterward regardless of outcome.
    """
    import sut.retriever as retriever_module

    original = getattr(retriever_module, attr)
    setattr(retriever_module, attr, value)
    try:
        passed = 0
        precisions: list[float] = []
        for benchmark in benchmarks:
            if benchmark.no_answer:
                continue
            chunks = retriever.retrieve(benchmark.query)
            score = score_retrieval(chunks, benchmark)
            precisions.append(score.source_precision)
            if score.passed:
                passed += 1
        n = len(precisions)
        return {
            "pass_rate": passed / n if n else 0.0,
            "mean_source_precision": sum(precisions) / n if n else 0.0,
        }
    finally:
        setattr(retriever_module, attr, original)


def run_sweep(
    retriever: Any, benchmarks: list[RetrievalBenchmark], attr: str, values: list[float]
) -> list[dict[str, float]]:
    """Sweep one retriever module constant across `values`, others held at default."""
    return [
        {"value": v, **_run_benchmarks_with_override(retriever, benchmarks, attr, v)}
        for v in values
    ]


def render_ablation_report(
    sweeps: dict[str, list[dict[str, float]]], defaults: dict[str, float]
) -> str:
    """Render a markdown ablation report from sweep results.

    sweeps: {param_name: [{"value": ..., "pass_rate": ..., "mean_source_precision": ...}, ...]}
    defaults: {param_name: current_default_value} — marks the row matching production config.
    """
    lines = [
        "# Retrieval Parameter Ablation",
        "",
        "Measures how `source_precision` and the benchmark pass rate in "
        "`datasets/retrieval/benchmarks.yaml` move as each hand-tuned retrieval "
        "constant in `src/sut/retriever.py` is varied, holding the other "
        "constants at their current default. Answers the caveat those "
        'constants carry in code: "hand-tuned starting point, not backed by '
        'a committed ablation study."',
        "",
        "Run against the real `PolicyRetriever` (local ONNX embeddings); "
        "`no_answer` benchmark cases are excluded from pass-rate/precision "
        "aggregation since they measure a different property (see "
        "`docs/known-issues.md`).",
        "",
    ]
    param_titles = {
        "_LEXICAL_WEIGHT": "Lexical overlap weight (`_LEXICAL_WEIGHT`)",
        "_DISTANCE_MARGIN": "Distance margin (`_DISTANCE_MARGIN`)",
        "_MAX_RELEVANT_DISTANCE": "No-answer distance ceiling (`_MAX_RELEVANT_DISTANCE`)",
    }
    for attr, rows in sweeps.items():
        lines += [
            f"## {param_titles.get(attr, attr)}",
            "",
            "| Value | Pass rate | Mean source precision |",
            "|---|---|---|",
        ]
        default_value = defaults.get(attr)
        for row in rows:
            marker = " *(current default)*" if row["value"] == default_value else ""
            lines.append(
                f"| {row['value']:.2f}{marker} | {row['pass_rate']:.0%} "
                f"| {row['mean_source_precision']:.3f} |"
            )
        lines.append("")
    lines += ["_Regenerate: `make retrieval-ablation`._", ""]
    return "\n".join(lines)


def run(out_path: Path = _DEFAULT_OUT_PATH, json_path: Path = _DEFAULT_JSON_PATH) -> str:
    from sut.retriever import PolicyRetriever

    benchmarks = load_retrieval_benchmarks()
    retriever = PolicyRetriever(RetrievalConfig())
    retriever.index_corpus()

    defaults = {
        "_LEXICAL_WEIGHT": 0.5,
        "_DISTANCE_MARGIN": 0.20,
        "_MAX_RELEVANT_DISTANCE": 0.45,
    }
    sweeps = {
        "_LEXICAL_WEIGHT": run_sweep(
            retriever, benchmarks, "_LEXICAL_WEIGHT", _LEXICAL_WEIGHT_SWEEP
        ),
        "_DISTANCE_MARGIN": run_sweep(
            retriever, benchmarks, "_DISTANCE_MARGIN", _DISTANCE_MARGIN_SWEEP
        ),
        "_MAX_RELEVANT_DISTANCE": run_sweep(
            retriever, benchmarks, "_MAX_RELEVANT_DISTANCE", _MAX_RELEVANT_DISTANCE_SWEEP
        ),
    }

    report = render_ablation_report(sweeps, defaults)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(sweeps, indent=2))

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(_DEFAULT_OUT_PATH), help="Report output path")
    parser.add_argument("--json-out", default=str(_DEFAULT_JSON_PATH), help="JSON output path")
    args = parser.parse_args()

    try:
        run(Path(args.out), Path(args.json_out))
    except Exception as exc:  # pragma: no cover - depends on local network/cache state
        print(f"Could not run retrieval ablation: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
