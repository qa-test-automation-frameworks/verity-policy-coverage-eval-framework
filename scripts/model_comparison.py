"""Compare two provider/model configurations on the golden set.

Usage:
  uv run python scripts/model_comparison.py \
    --left-provider zai --left-model glm-4.5 \
    --right-provider openrouter --right-model openai/gpt-4o-mini \
    --limit 5 --out reports/model-comparison.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sut.agent import CoverageAgent  # noqa: E402
from sut.retriever import PolicyRetriever  # noqa: E402
from verity.config import Provider, Settings  # noqa: E402
from verity.cost import RunAccumulator  # noqa: E402
from verity.golden import GoldenCase, load_golden  # noqa: E402
from verity.providers import LLMProvider  # noqa: E402

_DEFAULT_OUT = Path("reports/model-comparison.md")
_DEFAULT_JSON = Path("reports/model-comparison.json")


@dataclass(frozen=True)
class ModelResult:
    case_id: str
    provider: str
    model: str
    answered: bool
    refused: bool
    citation_count: int
    answer_chars: int
    error: str = ""


@dataclass(frozen=True)
class CaseComparison:
    case_id: str
    query: str
    behavior: str
    left: ModelResult
    right: ModelResult
    refusal_delta: bool
    citation_delta: int
    length_delta: int


def _settings(provider: str, model: str) -> Settings:
    return Settings(provider=Provider(provider), model=model, cassette_mode="off")


def _run_case(case: GoldenCase, settings: Settings) -> ModelResult:
    accumulator = RunAccumulator()
    retriever = PolicyRetriever(settings.retrieval)
    provider = LLMProvider(settings, accumulator)
    agent = CoverageAgent(settings=settings, retriever=retriever, provider=provider)
    try:
        response = agent.answer(case.query, member_id=case.member_id)
    except Exception as exc:  # live provider and local retrieval failures are report data
        return ModelResult(
            case_id=case.id,
            provider=settings.provider.value,
            model=settings.model,
            answered=False,
            refused=False,
            citation_count=0,
            answer_chars=0,
            error=str(exc),
        )
    return ModelResult(
        case_id=case.id,
        provider=settings.provider.value,
        model=settings.model,
        answered=bool(response.answer),
        refused=response.refused,
        citation_count=len(response.citations),
        answer_chars=len(response.answer),
    )


def compare_cases(cases: list[GoldenCase], left: Settings, right: Settings) -> list[CaseComparison]:
    rows: list[CaseComparison] = []
    for case in cases:
        left_result = _run_case(case, left)
        right_result = _run_case(case, right)
        rows.append(
            CaseComparison(
                case_id=case.id,
                query=case.query,
                behavior=case.behavior,
                left=left_result,
                right=right_result,
                refusal_delta=left_result.refused != right_result.refused,
                citation_delta=right_result.citation_count - left_result.citation_count,
                length_delta=right_result.answer_chars - left_result.answer_chars,
            )
        )
    return rows


def render_report(rows: list[CaseComparison], left_label: str, right_label: str) -> str:
    lines = [
        "# Model Comparison",
        "",
        f"Left: `{left_label}`  ",
        f"Right: `{right_label}`",
        "",
        "| Case | Expected behavior | Left refused | Right refused | Citation delta | Length delta | Errors |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        errors = "; ".join(e for e in (row.left.error, row.right.error) if e) or "-"
        lines.append(
            f"| `{row.case_id}` | {row.behavior} | {row.left.refused} | {row.right.refused} "
            f"| {row.citation_delta:+d} | {row.length_delta:+d} | {errors} |"
        )
    refusal_deltas = sum(1 for row in rows if row.refusal_delta)
    error_count = sum(1 for row in rows if row.left.error or row.right.error)
    lines += [
        "",
        "## Summary",
        "",
        f"- Cases compared: {len(rows)}",
        f"- Refusal behavior changed: {refusal_deltas}",
        f"- Cases with runtime errors: {error_count}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left-provider", required=True, choices=[p.value for p in Provider])
    parser.add_argument("--left-model", required=True)
    parser.add_argument("--right-provider", required=True, choices=[p.value for p in Provider])
    parser.add_argument("--right-model", required=True)
    parser.add_argument("--case", action="append", default=[], help="Golden case id to include")
    parser.add_argument("--limit", type=int, default=0, help="Maximum cases to run; 0 means all")
    parser.add_argument("--out", default=str(_DEFAULT_OUT))
    parser.add_argument("--json-out", default=str(_DEFAULT_JSON))
    args = parser.parse_args()

    cases = load_golden(Path("datasets/golden"))
    if args.case:
        wanted = set(args.case)
        cases = [case for case in cases if case.id in wanted]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("No golden cases selected")

    left = _settings(args.left_provider, args.left_model)
    right = _settings(args.right_provider, args.right_model)
    rows = compare_cases(cases, left, right)

    left_label = f"{args.left_provider}/{args.left_model}"
    right_label = f"{args.right_provider}/{args.right_model}"
    report = render_report(rows, left_label, right_label)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)

    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps([asdict(row) for row in rows], indent=2))
    print(f"Wrote {out} and {json_out}")


if __name__ == "__main__":
    main()
